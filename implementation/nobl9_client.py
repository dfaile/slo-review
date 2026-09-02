"""Read-only Nobl9 catalog client (access token + Objects API + Status API v2).

Used by `nobl9_catalog_lookup` to answer overlap questions: does this proposal
duplicate SLOs already deployed? Never writes objects. Never raises into the
agent — every public entry point returns `{error?, existing_slos}`.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping

# Origin only — paths below always include `/api/...`.
DEFAULT_BASE_URL = "https://app.nobl9.com"

# Nobl9 JWTs last one hour; refresh a minute early so in-flight calls don't 401.
TOKEN_TTL_SECONDS = 3600
TOKEN_REFRESH_SKEW_SECONDS = 60
# accessToken is limited to 1 request / 3 seconds per organization.
TOKEN_MIN_INTERVAL_SECONDS = 3.0

HTTP_TIMEOUT_SECONDS = 20.0

OBJECTS_PATH = "/api/v2/objects/v1alpha/slos"
STATUS_PATH = "/api/v2/slos"
TOKEN_PATH = "/api/accessToken"

# Nearby names are a hint for the model, not a full inventory.
MAX_NEARBY_SERVICES = 10


UrlOpen = Callable[..., Any]
SleepFn = Callable[[float], None]
ClockFn = Callable[[], float]


class CatalogError(Exception):
    """Structured HTTP/config failure; converted to `{error, existing_slos}`."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def credentials_configured(environ: Mapping[str, str] | None = None) -> bool:
    """True when the catalog tool should be registered (client ID + secret)."""
    env = environ if environ is not None else os.environ
    return bool(env.get("NOBL9_CLIENT_ID", "").strip() and env.get("NOBL9_CLIENT_SECRET", "").strip())


def normalize_base_url(url: str) -> str:
    """Accept `https://app.nobl9.com` or a mistaken `.../api` suffix."""
    cleaned = (url or DEFAULT_BASE_URL).strip().rstrip("/")
    if cleaned.endswith("/api"):
        cleaned = cleaned[:-4]
    return cleaned or DEFAULT_BASE_URL


def client_from_env(
    environ: Mapping[str, str] | None = None,
    **overrides: Any,
) -> Nobl9Client | None:
    """Build a client from env. Returns None when credentials are absent."""
    env = environ if environ is not None else os.environ
    client_id = env.get("NOBL9_CLIENT_ID", "").strip()
    client_secret = env.get("NOBL9_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    return Nobl9Client(
        client_id=client_id,
        client_secret=client_secret,
        organization=env.get("NOBL9_ORGANIZATION", "").strip(),
        base_url=normalize_base_url(env.get("NOBL9_URL", DEFAULT_BASE_URL)),
        default_project=env.get("NOBL9_PROJECT", "").strip(),
        **overrides,
    )


def lookup_catalog(
    service_name: str,
    project: str | None = None,
    *,
    client: Nobl9Client | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Tool-facing entry point. Never raises."""
    try:
        resolved = client if client is not None else client_from_env(environ)
        if resolved is None:
            return {
                "error": (
                    "Nobl9 catalog lookup is not configured. "
                    "Set NOBL9_CLIENT_ID and NOBL9_CLIENT_SECRET."
                ),
                "existing_slos": [],
            }
        return resolved.lookup(service_name, project)
    except Exception as exc:  # noqa: BLE001 — tool must not crash the agent
        return {"error": f"Nobl9 catalog lookup failed: {exc}", "existing_slos": []}


class Nobl9Client:
    """Thin urllib client with JWT cache and best-effort status join."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        organization: str = "",
        base_url: str = DEFAULT_BASE_URL,
        default_project: str = "",
        timeout: float = HTTP_TIMEOUT_SECONDS,
        urlopen: UrlOpen | None = None,
        sleep: SleepFn | None = None,
        clock: ClockFn | None = None,
        monotonic: ClockFn | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.organization = organization
        self.base_url = normalize_base_url(base_url)
        self.default_project = default_project
        self.timeout = timeout
        self._urlopen = urlopen or urllib.request.urlopen
        self._sleep = sleep or time.sleep
        self._clock = clock or time.time
        self._monotonic = monotonic or time.monotonic
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._last_token_monotonic: float = 0.0

    def lookup(self, service_name: str, project: str | None = None) -> dict[str, Any]:
        """List compact SLOs for a service. Never raises."""
        try:
            return self._lookup(service_name, project)
        except CatalogError as exc:
            return {"error": exc.message, "existing_slos": []}
        except Exception as exc:  # noqa: BLE001 — keep the review going
            return {"error": f"Nobl9 catalog lookup failed: {exc}", "existing_slos": []}

    def _lookup(self, service_name: str, project: str | None) -> dict[str, Any]:
        service = (service_name or "").strip()
        if not service:
            return {
                "error": "service_name is required (Nobl9 service name from the discovery doc).",
                "existing_slos": [],
            }

        resolved_project = (project or "").strip() or self.default_project
        if not resolved_project:
            return {
                "error": (
                    "A Nobl9 project is required. Pass project on the tool call "
                    "or set NOBL9_PROJECT."
                ),
                "existing_slos": [],
            }

        filtered = self._list_objects(project=resolved_project, service=service)
        unmatched = not filtered
        nearby: list[str] = []
        manifests = filtered
        if unmatched:
            # Service filter missed — show the project portfolio so the agent
            # can say "no Nobl9 service named X" instead of inventing catalog.
            manifests = self._list_objects(project=resolved_project, service=None)
            nearby = _nearby_services(manifests, service)

        status_by_key = self._status_index(resolved_project)
        existing = [
            compact_slo(manifest, status_by_key.get(_slo_key_from_manifest(manifest)))
            for manifest in manifests
        ]

        payload: dict[str, Any] = {
            "service_name": service,
            "project": resolved_project,
            "existing_slos": existing,
        }
        if unmatched:
            payload["unmatched_service"] = True
            payload["nearby_services"] = nearby
        return payload

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _list_objects(self, *, project: str, service: str | None) -> list[dict[str, Any]]:
        query: dict[str, str] = {"project": project}
        if service:
            query["service"] = service
        payload = self._json("GET", OBJECTS_PATH, query=query, auth="bearer")
        return _as_object_list(payload)

    def _status_index(self, project: str) -> dict[tuple[str, str], dict[str, Any]]:
        """Best-effort Status API v2 join. Failures yield an empty index."""
        try:
            payload = self._json("GET", STATUS_PATH, query={"project": project}, auth="bearer")
        except CatalogError:
            return {}
        except Exception:  # noqa: BLE001
            return {}
        index: dict[tuple[str, str], dict[str, Any]] = {}
        for row in _as_object_list(payload):
            key = _slo_key_from_status(row)
            if key:
                index[key] = row
        return index

    def _bearer_token(self) -> str:
        now = self._clock()
        if self._token and now < (self._token_expires_at - TOKEN_REFRESH_SKEW_SECONDS):
            return self._token

        elapsed = self._monotonic() - self._last_token_monotonic
        if self._last_token_monotonic and elapsed < TOKEN_MIN_INTERVAL_SECONDS:
            self._sleep(TOKEN_MIN_INTERVAL_SECONDS - elapsed)

        raw = self._json("POST", TOKEN_PATH, auth="basic")
        token = _extract_access_token(raw)
        if not token:
            raise CatalogError("Nobl9 accessToken response did not include a token.")
        self._token = token
        self._token_expires_at = self._clock() + TOKEN_TTL_SECONDS
        return token

    def _json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        auth: str,
    ) -> Any:
        url = self.base_url + path
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        headers = {
            "Accept": "application/json",
        }
        if self.organization:
            headers["Organization"] = self.organization

        if auth == "basic":
            blob = f"{self.client_id}:{self.client_secret}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(blob).decode("ascii")
        else:
            headers["Authorization"] = "Bearer " + self._bearer_token()

        request = urllib.request.Request(
            url,
            data=b"" if method == "POST" else None,
            headers=headers,
            method=method,
        )
        status, body = self._send(request)
        if status == 401:
            # Cached JWT may have been revoked — drop it and retry once.
            if auth == "bearer" and self._token:
                self._token = None
                self._token_expires_at = 0.0
                headers["Authorization"] = "Bearer " + self._bearer_token()
                request = urllib.request.Request(
                    url,
                    data=None,
                    headers=headers,
                    method=method,
                )
                status, body = self._send(request)
            if status == 401:
                raise CatalogError(
                    "Nobl9 authentication failed (401). "
                    "Check NOBL9_CLIENT_ID and NOBL9_CLIENT_SECRET.",
                    status=401,
                )
        if status == 429:
            raise CatalogError(
                "Nobl9 rate limited (429). Reuse the cached access token and retry later.",
                status=429,
            )
        if status < 200 or status >= 300:
            raise CatalogError(
                f"Nobl9 request failed ({status}) for {method} {path}.",
                status=status,
            )
        if body is None or body == "":
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise CatalogError(f"Nobl9 returned non-JSON from {method} {path}.") from exc

    def _send(self, request: urllib.request.Request) -> tuple[int, str]:
        is_token = urllib.parse.urlparse(request.full_url).path.rstrip("/").endswith("accessToken")
        try:
            response = self._urlopen(request, timeout=self.timeout)
            try:
                raw = response.read()
                status = int(getattr(response, "status", None) or response.getcode())
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
        except urllib.error.HTTPError as err:
            raw = err.read() if err.fp is not None else b""
            status = int(err.code)
        except urllib.error.URLError as err:
            raise CatalogError(f"Nobl9 request failed: {err.reason}") from err

        if is_token:
            self._last_token_monotonic = self._monotonic()

        if isinstance(raw, bytes):
            return status, raw.decode("utf-8", errors="replace")
        return status, str(raw)


def compact_slo(
    manifest: dict[str, Any],
    status_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collapse a full Objects-API manifest (+ optional status) into model context."""
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}
    time_window = _format_time_window(spec)
    objectives: list[dict[str, Any]] = []
    for obj in spec.get("objectives") or []:
        if not isinstance(obj, dict):
            continue
        objectives.append(
            {
                "name": obj.get("name") or obj.get("displayName") or "",
                "target": obj.get("target"),
                "time_window": time_window,
            }
        )

    row: dict[str, Any] = {
        "name": metadata.get("name") or "",
        "display_name": metadata.get("displayName") or metadata.get("display_name") or "",
        "project": metadata.get("project") or "",
        "service": spec.get("service") or "",
        "indicator_kind": _indicator_kind(spec),
        "metric_source_kind": _metric_source_kind(spec),
        "objectives": objectives,
    }
    joined = _status_fields(status_row)
    if joined:
        row.update(joined)
    return row


# ------------------------------------------------------------------
# Response shaping
# ------------------------------------------------------------------

def _as_object_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("slos", "data", "objects", "items"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [item for item in inner if isinstance(item, dict)]
    return []


def _extract_access_token(payload: Any) -> str:
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("access_token", "accessToken", "token"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _slo_key_from_manifest(manifest: dict[str, Any]) -> tuple[str, str]:
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    return (str(metadata.get("project") or ""), str(metadata.get("name") or ""))


def _slo_key_from_status(row: dict[str, Any]) -> tuple[str, str] | None:
    name = row.get("name") or ""
    project = row.get("project") or ""
    if not name and isinstance(row.get("metadata"), dict):
        name = row["metadata"].get("name") or ""
        project = project or row["metadata"].get("project") or ""
    if not name:
        return None
    return (str(project), str(name))


def _nearby_services(manifests: list[dict[str, Any]], requested: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    requested_l = requested.lower()
    for manifest in manifests:
        spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}
        service = str(spec.get("service") or "").strip()
        if not service or service.lower() == requested_l or service in seen:
            continue
        seen.add(service)
        names.append(service)
        if len(names) >= MAX_NEARBY_SERVICES:
            break
    names.sort()
    return names


def _indicator_kind(spec: dict[str, Any]) -> str:
    if spec.get("composite"):
        return "Composite"
    indicator = spec.get("indicator") if isinstance(spec.get("indicator"), dict) else {}
    if indicator.get("rawMetric"):
        return "Threshold"
    objectives = spec.get("objectives") or []
    if any(isinstance(obj, dict) and obj.get("countMetrics") for obj in objectives):
        return "Ratio"
    return "Unknown"


def _metric_source_kind(spec: dict[str, Any]) -> str:
    indicator = spec.get("indicator") if isinstance(spec.get("indicator"), dict) else {}
    source = indicator.get("metricSource") if isinstance(indicator.get("metricSource"), dict) else {}
    return str(source.get("kind") or "")


def _format_time_window(spec: dict[str, Any]) -> str:
    windows = spec.get("timeWindows") or []
    if not windows or not isinstance(windows[0], dict):
        return ""
    window = windows[0]
    count = window.get("count", "")
    unit = str(window.get("unit") or "")
    abbr = {"Day": "d", "Hour": "h", "Minute": "m", "Week": "w", "Month": "mo"}.get(unit, unit.lower())
    stamp = f"{count}{abbr}"
    if window.get("isRolling"):
        return f"{stamp} rolling"
    if window.get("calendar"):
        return f"{stamp} calendar"
    return stamp


def _status_fields(status_row: dict[str, Any] | None) -> dict[str, Any]:
    """Lift worst-objective reliability / remaining budget onto the compact SLO."""
    if not status_row:
        return {}
    objectives = status_row.get("objectives") or []
    reliabilities: list[float] = []
    remaining: list[float] = []
    statuses: list[str] = []
    for obj in objectives:
        if not isinstance(obj, dict):
            continue
        rel = _first_number(obj, ("reliability",), nested=("sli",))
        if rel is not None:
            reliabilities.append(rel)
        budget = obj.get("errorBudget") if isinstance(obj.get("errorBudget"), dict) else {}
        alt_budget = obj.get("budget") if isinstance(obj.get("budget"), dict) else {}
        rem = _first_number(
            obj,
            ("errorBudgetRemaining", "remainingErrorBudget", "remaining_budget"),
        )
        if rem is None:
            rem = _first_number(budget, ("remaining", "remainingPercentage"))
        if rem is None:
            rem = _first_number(alt_budget, ("remaining",))
        if rem is not None:
            remaining.append(rem)
        label = (
            budget.get("status")
            or alt_budget.get("status")
            or obj.get("budgetStatus")
            or obj.get("budget_status")
        )
        if isinstance(label, str) and label:
            statuses.append(label)

    if not reliabilities and not remaining and not statuses:
        return {}

    fields: dict[str, Any] = {}
    if reliabilities:
        fields["reliability"] = min(reliabilities)
    if remaining:
        fields["remaining_budget"] = min(remaining)
    if statuses:
        rank = {"exhausted": 0, "atrisk": 1, "at_risk": 1, "ok": 2}
        fields["budget_status"] = min(statuses, key=lambda s: rank.get(s.lower().replace(" ", ""), 9))
    elif remaining:
        fields["budget_status"] = "Exhausted" if min(remaining) <= 0 else "Ok"
    return fields


def _first_number(
    row: dict[str, Any],
    keys: tuple[str, ...],
    *,
    nested: tuple[str, ...] = (),
) -> float | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    for nested_key in nested:
        inner = row.get(nested_key)
        if isinstance(inner, dict):
            found = _first_number(inner, keys)
            if found is not None:
                return found
    return None
