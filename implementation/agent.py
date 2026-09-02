"""
SLO Review Board Agent
======================

Reference Agent Development Kit (ADK) implementation of the SLO Approval
Review agent. Deployable to Vertex AI Agent Engine.

Architecture:
- Primary agent: gemini-3.1-pro for principal-SRE reasoning
- Skills: slo-approval-review (always loaded), sre-principles-citation (conditional)
- Tools: ingest_documents, search_sre_corpus, (optional) nobl9_catalog_lookup

Deploy:
    adk deploy agent_engine --agent slo_review_agent.agent --region us-central1

Test locally:
    adk web .

License: Apache-2.0. SRE Book/Workbook grounding is CC BY-NC-ND 4.0 — do not
redistribute book text verbatim.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from google.adk import Agent
from google.adk.tools import FunctionTool
from google.adk.skills import SkillToolset, Skill, Frontmatter
from google.cloud import discoveryengine_v1
from google.cloud import storage
from pydantic import BaseModel, Field

from nobl9_client import client_from_env, credentials_configured, lookup_catalog


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
REGION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
# DEPLOYMENT_VERTICAL is canonical; CUSTOMER_VERTICAL is accepted so older env files still work.
VERTICAL = os.environ.get("DEPLOYMENT_VERTICAL") or os.environ.get("CUSTOMER_VERTICAL", "horizontal")

# Reused across tool calls in this process so the JWT is fetched once per hour.
_nobl9_client = None

PROMPT_DIR = Path(__file__).parent / "prompts"
SKILLS_DIR = Path(__file__).parent / "skills"

# Vertex AI Search datastore IDs (provisioned per deployment)
DOCS_DATASTORE_ID = os.environ.get("SLO_REVIEW_DOCS_DATASTORE", "")
SRE_CORPUS_DATASTORE_ID = os.environ.get("SLO_REVIEW_SRE_CORPUS_DATASTORE", "")


def _require_config(name: str, value: str) -> str:
    """Fail at tool-call time with a clear message instead of at import."""
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill in Google Cloud values."
        )
    return value


# ---------------------------------------------------------------------------
# Structured output schema — used to expose machine-readable verdicts for
# downstream integrations (Slack notifications, ServiceNow tickets, etc.)
# ---------------------------------------------------------------------------

class SLOEvaluation(BaseModel):
    name: str = Field(description="The proposed SLO name.")
    proposed_target: str = Field(description="The target as written in the implementation guide.")
    status: str = Field(description="Approved | Conditional | Rejected")
    rationale: str = Field(description="One-line explanation of the status.")


class ReviewVerdict(BaseModel):
    """Machine-readable verdict, emitted alongside the human-readable Markdown paper."""
    verdict: str = Field(description="Approved | Approved with Revisions | Rejected — Recommend Rescope")
    service_name: str
    slo_evaluations: list[SLOEvaluation]
    gaps: list[str]
    excess: list[str]
    sign_off_conditions: list[str]
    full_paper_markdown: str = Field(description="The complete review paper.")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def ingest_documents(gcs_prefix: str) -> dict[str, Any]:
    """Retrieve SLO discovery and implementation guide documents from a Cloud Storage prefix.

    Convention: one prefix per service. Discovery doc should match *discovery*.md
    or *discovery*.pdf; implementation guide should match *impl*.md or *guide*.pdf.

    Args:
        gcs_prefix: e.g. "gs://your-bucket/slo-review/checkout-service/"

    Returns:
        dict with keys "discovery" and "implementation_guide", each containing
        the document text content.
    """
    client = storage.Client(project=_require_config("GOOGLE_CLOUD_PROJECT", PROJECT_ID))
    bucket_name, _, prefix = gcs_prefix.replace("gs://", "").partition("/")
    bucket = client.bucket(bucket_name)

    discovery_text = None
    impl_text = None

    for blob in bucket.list_blobs(prefix=prefix):
        name_lower = blob.name.lower()
        if "discovery" in name_lower and not discovery_text:
            discovery_text = blob.download_as_text()
        elif ("impl" in name_lower or "guide" in name_lower) and not impl_text:
            impl_text = blob.download_as_text()

    return {
        "discovery": discovery_text or "[Not found at the given prefix]",
        "implementation_guide": impl_text or "[Not found at the given prefix]",
        "source_prefix": gcs_prefix,
    }


def search_sre_corpus(query: str, max_results: int = 3) -> dict[str, Any]:
    """Search the Google SRE Book, SRE Workbook, and org-specific reliability standards.

    Use only when grounding a critique requires citing the source framework. Do not
    use for routine reviews — the system prompt already contains the framework.

    Args:
        query: Natural-language query (e.g. "symptoms vs causes SLI definition")
        max_results: How many passages to return. Default 3.

    Returns:
        dict with "passages" list, each containing "title", "excerpt", "source_uri".
    """
    client = discoveryengine_v1.SearchServiceClient()
    datastore_id = _require_config("SLO_REVIEW_SRE_CORPUS_DATASTORE", SRE_CORPUS_DATASTORE_ID)
    project_id = _require_config("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
    serving_config = (
        f"projects/{project_id}/locations/global/collections/default_collection/"
        f"dataStores/{datastore_id}/servingConfigs/default_config"
    )

    request = discoveryengine_v1.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=max_results,
    )

    response = client.search(request=request)
    passages = []
    for result in response.results:
        doc = result.document
        passages.append({
            "title": doc.derived_struct_data.get("title", "Untitled"),
            "excerpt": doc.derived_struct_data.get("snippets", [""])[0],
            "source_uri": doc.derived_struct_data.get("link", ""),
        })

    return {"passages": passages, "query": query}


def nobl9_catalog_lookup(service_name: str, project: str = "") -> dict[str, Any]:
    """Look up SLOs already deployed in Nobl9 for overlap with this proposal.

    Call when Nobl9 is mentioned, when the user asks about overlap or
    already-deployed SLOs, or when a proposal looks like it might duplicate
    an existing portfolio. Read-only — does not apply or generate YAML.

    Args:
        service_name: Nobl9 service name from the discovery document.
        project: Nobl9 project. Falls back to NOBL9_PROJECT if omitted.

    Returns:
        Compact catalog payload: existing_slos (name, targets, optional live
        reliability / remaining budget). On failure, {error, existing_slos: []}
        so the review can continue without inventing catalog.
    """
    global _nobl9_client
    if _nobl9_client is None:
        _nobl9_client = client_from_env()
    return lookup_catalog(service_name, project or None, client=_nobl9_client)


# ---------------------------------------------------------------------------
# Skill: slo-approval-review (the SKILL.md content, ported to ADK Skill format)
# ---------------------------------------------------------------------------

def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


slo_approval_review_skill = Skill(
    frontmatter=Frontmatter(
        name="slo-approval-review",
        description=(
            "Principal-SRE review of an SLO Implementation Guide against an "
            "SLO Discovery document. Produces a verdict (Approved / Approved "
            "with Revisions / Rejected) with SLO-by-SLO evaluation, gaps, "
            "excess, and sign-off conditions."
        ),
    ),
    instructions=_load_text(SKILLS_DIR / "slo-approval-review" / "SKILL.md"),
)

sre_principles_skill = Skill(
    frontmatter=Frontmatter(
        name="sre-principles-citation",
        description=(
            "On-demand citations from the Google SRE Book and SRE Workbook "
            "for the four review principles (symptoms vs causes, SLO count "
            "discipline, target validity, dependency ceiling). Load only "
            "when a citation is needed to ground a critique."
        ),
    ),
    instructions=_load_text(SKILLS_DIR / "sre-principles-citation" / "SKILL.md"),
)

skill_toolset = SkillToolset(skills=[slo_approval_review_skill, sre_principles_skill])


# ---------------------------------------------------------------------------
# System instruction: the master prompt with vertical customization prepended
# ---------------------------------------------------------------------------

def _build_system_instruction() -> str:
    base_prompt = _load_text(PROMPT_DIR / "system.md")

    vertical_prepend = ""
    if VERTICAL != "horizontal":
        vertical_file = PROMPT_DIR / f"vertical-{VERTICAL}.md"
        if vertical_file.exists():
            vertical_prepend = _load_text(vertical_file) + "\n\n"

    return vertical_prepend + base_prompt


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------

def _tool_functions() -> list:
    """Callables to wrap as FunctionTools. Catalog lookup is credential-gated."""
    functions = [ingest_documents, search_sre_corpus]
    if credentials_configured():
        functions.append(nobl9_catalog_lookup)
    return functions


def _build_tools() -> list[FunctionTool]:
    return [FunctionTool(fn) for fn in _tool_functions()]


agent = Agent(
    name="slo_review_board_agent",
    model="gemini-3.1-pro",
    description=(
        "Reviews SLO implementation proposals against discovery documents and "
        "renders a principal-SRE approval verdict."
    ),
    instruction=_build_system_instruction(),
    tools=_build_tools(),
    skills=skill_toolset,
    generate_content_config={
        "temperature": 0.2,
        "top_p": 0.95,
        "max_output_tokens": 8192,
    },
    # Output schema is exposed for programmatic consumers (Slack bot, ServiceNow
    # integration) while the human-readable Markdown paper remains the primary output.
    output_schema=ReviewVerdict,
)


# ---------------------------------------------------------------------------
# Local CLI / web entry point for development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Use `adk web .` from this directory for an interactive UI.
    # This block exists to make the file directly runnable for smoke testing.
    print("SLO Review Board Agent loaded.")
    print(f"  Model: {agent.model}")
    print(f"  Vertical: {VERTICAL}")
    print(f"  Nobl9 catalog: {'enabled' if credentials_configured() else 'disabled (no client credentials)'}")
    print(f"  Tools: {[getattr(t, 'name', None) for t in agent.tools]}")
    print(f"  Skills: {[s.frontmatter.name for s in skill_toolset.skills]}")
    print()
    print("To run interactively: `adk web .` from this directory.")
    print("To deploy: `adk deploy agent_engine --agent agent.agent`")
