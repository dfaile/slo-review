"""Mocked Nobl9 catalog client tests. Public CI must not hit a real org."""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
import unittest
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

IMPL_DIR = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "nobl9_responses.json"

# Allow `import nobl9_client` / `import agent` from implementation/.
if str(IMPL_DIR) not in sys.path:
    sys.path.insert(0, str(IMPL_DIR))

from nobl9_client import (  # noqa: E402
    Nobl9Client,
    compact_slo,
    credentials_configured,
    lookup_catalog,
)


def _load_fixtures() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        if isinstance(payload, (bytes, bytearray)):
            self._raw = bytes(payload)
        else:
            self._raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._raw

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        return None


class FakeNobl9:
    """urlopen stand-in that records calls and serves fixture JSON."""

    def __init__(self, fixtures: dict[str, Any] | None = None) -> None:
        self.fixtures = fixtures or _load_fixtures()
        self.calls: list[tuple[str, str, dict[str, list[str]]]] = []
        self.token_status = 200
        self.token_body: Any = {"access_token": "test-jwt"}
        self.objects_status = 200
        self.status_status = 200
        self.status_body: Any = self.fixtures["status_checkout"]
        self.token_posts = 0

    def urlopen(self, request: Request, timeout: float | None = None) -> FakeResponse:
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        method = request.get_method()
        self.calls.append((method, parsed.path, query))

        if parsed.path.rstrip("/").endswith("accessToken"):
            self.token_posts += 1
            return self._respond(self.token_status, self.token_body, request.full_url)

        if parsed.path.endswith("/objects/v1alpha/slos"):
            service = (query.get("service") or [None])[0]
            if service == "checkout-service":
                body: Any = self.fixtures["objects_checkout"]
            elif service:
                body = []
            else:
                body = self.fixtures["objects_project_wide"]
            return self._respond(self.objects_status, body, request.full_url)

        if parsed.path.endswith("/slos") or parsed.path.endswith("/api/v2/slos"):
            return self._respond(self.status_status, self.status_body, request.full_url)

        return self._respond(404, {"error": "not found"}, request.full_url)

    def _respond(self, status: int, body: Any, url: str) -> FakeResponse:
        if status >= 400:
            raw = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
            raise HTTPError(url, status, "error", hdrs=None, fp=BytesIO(raw))
        return FakeResponse(body, status=status)


def _client(fake: FakeNobl9, **kwargs: Any) -> Nobl9Client:
    return Nobl9Client(
        client_id="id",
        client_secret="secret",
        organization="acme",
        default_project="payments",
        urlopen=fake.urlopen,
        sleep=lambda _seconds: None,
        **kwargs,
    )


class CredentialsTests(unittest.TestCase):
    def test_tool_not_enabled_when_credentials_absent(self) -> None:
        self.assertFalse(credentials_configured({}))
        self.assertFalse(credentials_configured({"NOBL9_CLIENT_ID": "only-id"}))
        self.assertFalse(credentials_configured({"NOBL9_CLIENT_SECRET": "only-secret"}))

    def test_tool_enabled_when_client_id_and_secret_set(self) -> None:
        self.assertTrue(
            credentials_configured(
                {"NOBL9_CLIENT_ID": "id", "NOBL9_CLIENT_SECRET": "secret"}
            )
        )

    def test_lookup_without_credentials_is_structured_error(self) -> None:
        result = lookup_catalog("checkout-service", environ={})
        self.assertIn("not configured", result["error"])
        self.assertEqual(result["existing_slos"], [])


class TokenCacheTests(unittest.TestCase):
    def test_token_cached_and_reused_across_lookups(self) -> None:
        fake = FakeNobl9()
        client = _client(fake)
        first = client.lookup("checkout-service", project="payments")
        second = client.lookup("checkout-service", project="payments")
        self.assertNotIn("error", first)
        self.assertNotIn("error", second)
        self.assertEqual(fake.token_posts, 1)
        token_calls = [c for c in fake.calls if c[1].rstrip("/").endswith("accessToken")]
        self.assertEqual(len(token_calls), 1)


class ServiceFilterTests(unittest.TestCase):
    def test_service_filter_returns_compact_checkout_slos(self) -> None:
        fake = FakeNobl9()
        result = _client(fake).lookup("checkout-service", project="payments")
        names = [slo["name"] for slo in result["existing_slos"]]
        self.assertEqual(names, ["checkout-success", "checkout-latency"])
        self.assertNotIn("unmatched_service", result)
        checkout = result["existing_slos"][0]
        self.assertEqual(checkout["service"], "checkout-service")
        self.assertEqual(checkout["project"], "payments")
        self.assertEqual(checkout["indicator_kind"], "Ratio")
        self.assertEqual(checkout["metric_source_kind"], "Direct")
        self.assertEqual(checkout["objectives"][0]["target"], 0.999)
        self.assertEqual(checkout["objectives"][0]["time_window"], "28d rolling")

    def test_unmatched_service_falls_back_to_project_list(self) -> None:
        fake = FakeNobl9()
        result = _client(fake).lookup("does-not-exist", project="payments")
        self.assertTrue(result["unmatched_service"])
        self.assertIn("user-service", result["nearby_services"])
        self.assertIn("checkout-service", result["nearby_services"])
        names = {slo["name"] for slo in result["existing_slos"]}
        self.assertIn("user-service-availability", names)
        object_calls = [c for c in fake.calls if c[1].endswith("/objects/v1alpha/slos")]
        self.assertEqual(len(object_calls), 2)
        self.assertEqual(object_calls[0][2].get("service"), ["does-not-exist"])
        self.assertNotIn("service", object_calls[1][2])


class StatusJoinTests(unittest.TestCase):
    def test_status_fields_joined_onto_compact_slo(self) -> None:
        fake = FakeNobl9()
        result = _client(fake).lookup("checkout-service", project="payments")
        by_name = {slo["name"]: slo for slo in result["existing_slos"]}
        self.assertEqual(by_name["checkout-success"]["reliability"], 0.9987)
        self.assertEqual(by_name["checkout-success"]["remaining_budget"], 0.42)
        self.assertEqual(by_name["checkout-success"]["budget_status"], "Ok")
        self.assertEqual(by_name["checkout-latency"]["budget_status"], "AtRisk")

    def test_status_500_still_returns_definitions(self) -> None:
        fake = FakeNobl9()
        fake.status_status = 500
        result = _client(fake).lookup("checkout-service", project="payments")
        self.assertNotIn("error", result)
        names = [slo["name"] for slo in result["existing_slos"]]
        self.assertIn("checkout-success", names)
        self.assertNotIn("reliability", result["existing_slos"][0])


class ErrorMappingTests(unittest.TestCase):
    def test_401_becomes_structured_error(self) -> None:
        fake = FakeNobl9()
        fake.token_status = 401
        result = _client(fake).lookup("checkout-service", project="payments")
        self.assertIn("401", result["error"])
        self.assertEqual(result["existing_slos"], [])

    def test_429_becomes_structured_error(self) -> None:
        fake = FakeNobl9()
        fake.objects_status = 429
        result = _client(fake).lookup("checkout-service", project="payments")
        self.assertIn("429", result["error"])
        self.assertEqual(result["existing_slos"], [])

    def test_missing_project_asks_for_project(self) -> None:
        fake = FakeNobl9()
        client = Nobl9Client(
            client_id="id",
            client_secret="secret",
            urlopen=fake.urlopen,
            sleep=lambda _seconds: None,
        )
        result = client.lookup("checkout-service", project="")
        self.assertIn("project", result["error"].lower())
        self.assertEqual(fake.token_posts, 0)


class OverlapEvalFixtureTests(unittest.TestCase):
    def test_compact_payload_contains_overlapping_checkout_success(self) -> None:
        """Eval case-07 documents overlap; the compact payload must name the live SLO."""
        fake = FakeNobl9()
        result = _client(fake).lookup("checkout-service", project="payments")
        names = [slo["name"] for slo in result["existing_slos"]]
        self.assertIn("checkout-success", names)
        compact = compact_slo(_load_fixtures()["objects_checkout"][0])
        self.assertEqual(compact["name"], "checkout-success")
        evals = json.loads((IMPL_DIR / "evals" / "evals.json").read_text(encoding="utf-8"))
        case = next(c for c in evals["cases"] if c["id"] == "case-07-overlap-existing-nobl9-slo")
        fixture_names = [slo["name"] for slo in case["catalog_fixture"]["existing_slos"]]
        self.assertIn("checkout-success", fixture_names)
        self.assertTrue(any("overlap" in finding.lower() for finding in case["required_findings"]))


def _install_import_stubs() -> None:
    """Make `import agent` work without ADK / pydantic installed."""
    try:
        import pydantic  # noqa: F401
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **kwargs: Any) -> None:
                self.__dict__.update(kwargs)

        def Field(*_args: Any, **_kwargs: Any) -> None:
            return None

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

    try:
        import google.adk  # noqa: F401
        return
    except ImportError:
        pass

    def _pkg(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = mod
        return mod

    google = _pkg("google")
    adk = _pkg("google.adk")
    adk_tools = _pkg("google.adk.tools")
    adk_skills = _pkg("google.adk.skills")
    _pkg("google.cloud")
    _pkg("google.cloud.discoveryengine_v1")
    _pkg("google.cloud.storage")

    class FunctionTool:
        def __init__(self, fn: Any) -> None:
            self.fn = fn
            self.name = fn.__name__

    class Agent:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class Frontmatter:
        def __init__(self, name: str, description: str) -> None:
            self.name = name
            self.description = description

    class Skill:
        def __init__(self, frontmatter: Any, instructions: str) -> None:
            self.frontmatter = frontmatter
            self.instructions = instructions

    class SkillToolset:
        def __init__(self, skills: list) -> None:
            self.skills = skills

    google.adk = adk
    adk.Agent = Agent
    adk.tools = adk_tools
    adk.skills = adk_skills
    adk_tools.FunctionTool = FunctionTool
    adk_skills.SkillToolset = SkillToolset
    adk_skills.Skill = Skill
    adk_skills.Frontmatter = Frontmatter


class ToolRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _install_import_stubs()
        # Import once. Registration is decided at _tool_functions() call time.
        cls.agent_mod = importlib.import_module("agent")

    def test_catalog_tool_not_registered_without_credentials(self) -> None:
        with patch.dict(
            os.environ,
            {"NOBL9_CLIENT_ID": "", "NOBL9_CLIENT_SECRET": ""},
            clear=False,
        ):
            names = [fn.__name__ for fn in self.agent_mod._tool_functions()]
            self.assertIn("ingest_documents", names)
            self.assertIn("search_sre_corpus", names)
            self.assertNotIn("nobl9_catalog_lookup", names)

    def test_catalog_tool_registered_when_credentials_set(self) -> None:
        with patch.dict(
            os.environ,
            {"NOBL9_CLIENT_ID": "id", "NOBL9_CLIENT_SECRET": "secret"},
            clear=False,
        ):
            names = [fn.__name__ for fn in self.agent_mod._tool_functions()]
            self.assertIn("nobl9_catalog_lookup", names)


if __name__ == "__main__":
    unittest.main()
