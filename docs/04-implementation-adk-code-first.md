# 04 — Implementation: ADK Code-First (Python)

This is the production path. Choose this when you need CI/CD, programmatic eval, or embedded workflows. Target time: **one engineering day for a clean deployment, longer if you wire Slack/GitHub/ServiceNow.**

The companion code is `../implementation/agent.py`. Read this document alongside that directory.

---

## Why Code-First (vs. Agent Studio)

You give up the GUI. You get:

1. **Version control.** System prompt, tools, skills, and config all live in git. Every prompt change is a PR.
2. **Programmatic eval.** Run `evals.json` against the agent in CI before any prompt change reaches production.
3. **Embeddability.** Ship as a Python library. Wrap in a Cloud Run service. Bundle into a Slack app. Drop into a ServiceNow Now Assist plugin.
4. **Config via environment.** Datastore IDs, region, and optional vertical prepends are env vars; no separate Studio agent per environment.

The only reason to stay in Agent Studio is if operators explicitly want admin GUI control. Default to ADK for anything you intend to keep.

---

## Project Layout

```
implementation/
├── agent.py                    # ADK agent definition
├── nobl9_client.py             # Read-only Nobl9 REST client
├── requirements.txt
├── prompts/
│   ├── system.md               # Master system prompt (from 02-master-system-prompt.md)
│   ├── vertical-gxp.md
│   ├── vertical-fedramp.md
│   └── vertical-pci.md
├── skills/
│   ├── slo-approval-review/
│   │   └── SKILL.md
│   └── sre-principles-citation/
│       └── SKILL.md
├── tests/
│   └── test_nobl9_client.py    # Mocked catalog client + tool registration
└── evals/
    └── evals.json              # Golden eval set
```

Run `adk web .` and `python agent.py` from `implementation/`. The eval runner specified in `05-evaluation-and-guardrails.md` is not shipped yet — wire it to your ADK runtime before treating prompt changes as production-ready.

---

## Prerequisites

```bash
# Python 3.11+ recommended
python --version

# Install ADK and the supporting Google Cloud libraries
pip install -r implementation/requirements.txt

# Authenticate
gcloud auth application-default login
gcloud config set project [YOUR_PROJECT]

# Enable APIs (one-time per project)
gcloud services enable aiplatform.googleapis.com \
                       discoveryengine.googleapis.com \
                       storage.googleapis.com
```

Use a service account with `roles/aiplatform.user`, `roles/discoveryengine.user`, and read access to the docs bucket.

---

## Step 1 — Place the System Prompt and Skills

Take the prompt body from `02-master-system-prompt.md` (just the code-fenced block — not the surrounding explanation) and save it as:

```
prompts/system.md
```

Take the existing `slo-approval-review` SKILL.md content and save it as:

```
skills/slo-approval-review/SKILL.md
```

Create a smaller `sre-principles-citation/SKILL.md` containing exact quotes from the SRE Book and SRE Workbook on each of the four review principles. (This is the on-demand citation skill that gets loaded only when the agent needs to ground a critique.)

For vertical-specific deployments, save the appropriate prepend from `02-master-system-prompt.md` Vertical Customization section as `prompts/vertical-[name].md`.

---

## Step 2 — Provision Vertex AI Search Datastores

You need two datastores:

```bash
# Datastore 1: discovery + impl guide uploads
gcloud discovery-engine data-stores create slo-review-docs \
    --location=global \
    --solution-type=SOLUTION_TYPE_SEARCH \
    --industry-vertical=GENERIC

# Datastore 2: the SRE corpus (Google SRE Book + org-specific standards)
gcloud discovery-engine data-stores create slo-review-sre-corpus \
    --location=global \
    --solution-type=SOLUTION_TYPE_SEARCH \
    --industry-vertical=GENERIC
```

Then ingest:

```bash
# Review docs are indexed live from the GCS bucket where users upload
gcloud discovery-engine documents import \
    --data-store=slo-review-docs \
    --source=gs://[your-bucket]/slo-review/ \
    --reconciliation-mode=INCREMENTAL

# SRE corpus is ingested once (or whenever you update the corpus)
gcloud discovery-engine documents import \
    --data-store=slo-review-sre-corpus \
    --source=gs://[your-bucket]/sre-corpus/
```

Keep the SRE corpus in a separate datastore from review-document uploads. Do not commingle tenants if you run more than one organization.

---

## Step 3 — Configure Environment

Copy `.env.example` to `.env` and fill in:

```bash
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_REGION=us-central1
SLO_REVIEW_DOCS_DATASTORE=slo-review-docs
SLO_REVIEW_SRE_CORPUS_DATASTORE=slo-review-sre-corpus
DEPLOYMENT_VERTICAL=horizontal                 # or gxp / fedramp / pci

# Optional — registers nobl9_catalog_lookup when both credentials are set
NOBL9_CLIENT_ID=
NOBL9_CLIENT_SECRET=
NOBL9_ORGANIZATION=
NOBL9_URL=https://app.nobl9.com                 # EU: https://app.nobl9.eu
NOBL9_PROJECT=                                 # default project if the tool call omits one
```

`nobl9_catalog_lookup` is registered only when `NOBL9_CLIENT_ID` and `NOBL9_CLIENT_SECRET` are set. There is no `DEPLOYMENT_TIER` gate. The client POSTs `/api/accessToken` with Basic auth, caches the JWT for about an hour (refresh 60s early), and respects Nobl9's 1 token request / 3 seconds limit. It then GETs Objects API SLO manifests and, best-effort, joins Status API v2 remaining budget / reliability. Store the client secret in Secret Manager — never in git:

```bash
gcloud secrets create nobl9-client-secret --data-file=- < your-client-secret.txt
```

Reference that secret in the agent's runtime configuration when deployed. The agent never applies or generates Nobl9 YAML.

---

## Step 4 — Test Locally

```bash
# Launches the ADK web UI at http://localhost:8000
adk web slo_review_agent
```

You'll get a chat interface. Upload sample docs to your test GCS bucket, then ask the agent:

```
Review the SLOs at gs://test-bucket/slo-review/checkout-service/
```

The agent should:

1. Call `ingest_documents` with the GCS prefix
2. Read both docs
3. Optionally call `nobl9_catalog_lookup` when Nobl9 / overlap is in play
4. Optionally call `search_sre_corpus` if it needs grounding
5. Return a Markdown review paper + structured ReviewVerdict

Inspect the tool-call trace in the UI. If the agent skipped `ingest_documents` or invented document content, the system prompt isn't loaded correctly — check `prompts/system.md` and the `_build_system_instruction()` function.

---

## Step 5 — Run the Eval Suite

The runner is specified in `05-evaluation-and-guardrails.md` but is **not shipped** yet. The golden cases live in `implementation/evals/evals.json`. Wire a runner to your ADK runtime, then assert:

- Verdict is in the first sentence
- Verdict matches the golden verdict for each eval case
- All proposed SLOs are evaluated
- Output stays under 1500 words
- The agent does not soften verdicts under adversarial follow-up turns

Eval failures should block deployment. Wire this into CI.

---

## Step 6 — Deploy to Agent Engine

```bash
adk deploy agent_engine \
    --agent slo_review_agent.agent \
    --display-name "SLO Review Board Agent" \
    --region us-central1 \
    --requirements requirements.txt \
    --env-vars-file .env.production
```

Deploy takes 5–10 minutes. The output gives you the engine resource name:

```
projects/[project]/locations/us-central1/reasoningEngines/[engine-id]
```

That's your production endpoint. From here, anything that can speak the Agent Engine API can call it.

---

## Step 7 — Integration Patterns

### Pattern A: Slack App

```python
# slack_integration/handler.py
from slack_bolt import App
from vertexai.preview import reasoning_engines

app = App(token=os.environ["SLACK_BOT_TOKEN"])
engine = reasoning_engines.ReasoningEngine(
    os.environ["AGENT_ENGINE_RESOURCE_NAME"]
)

@app.command("/slo-review")
def handle_review(ack, command, say):
    ack()
    gcs_uri = command["text"].strip()
    response = engine.query(input={
        "messages": [{"role": "user", "content": f"Review the SLOs at {gcs_uri}"}]
    })
    say(blocks=[
        {"type": "section", "text": {"type": "mrkdwn", "text": response["output"]["full_paper_markdown"]}}
    ])
```

This is the most common production deployment. SRE teams live in Slack; the bot fits their existing workflow.

### Pattern B: GitHub Actions on SLO Config PRs

Trigger the agent every time a PR to an SLO config repo opens. The agent reviews the proposed YAML against the discovery doc stored in the repo.

```yaml
# .github/workflows/slo-review.yml
name: SLO Review
on:
  pull_request:
    paths:
      - 'slo-configs/**'
      - 'discovery/**'

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run SLO Review Agent
        run: |
          python scripts/run_review.py \
            --discovery discovery/${{ inputs.service }}.md \
            --impl-guide slo-configs/${{ inputs.service }}/impl-guide.md \
            --output reviews/${{ github.sha }}.md
      - name: Post review as PR comment
        uses: peter-evans/create-or-update-comment@v3
        with:
          issue-number: ${{ github.event.pull_request.number }}
          body-path: reviews/${{ github.sha }}.md
```

SRE teams that already gate config in GitHub can attach this as a PR comment.

### Pattern C: ServiceNow Workflow

For teams running their SRE program out of ServiceNow's SAM / IRM modules. Use ServiceNow's Now Assist custom skill plugin to register the Agent Engine endpoint as a callable backend.

### Pattern D: Direct API for an internal portal

For an internal SRE portal, expose a simple FastAPI wrapper:

```python
# api/main.py
from fastapi import FastAPI
from vertexai.preview import reasoning_engines

app = FastAPI()
engine = reasoning_engines.ReasoningEngine(os.environ["AGENT_ENGINE_RESOURCE_NAME"])

@app.post("/review")
async def review(gcs_uri: str):
    response = engine.query(input={
        "messages": [{"role": "user", "content": f"Review the SLOs at {gcs_uri}"}]
    })
    return response["output"]
```

Wrap in Cloud Run, IAM-protect the endpoint, done.

---

## CI/CD Workflow

The intended pipeline:

```
┌────────────┐    ┌──────────┐    ┌─────────┐    ┌────────────┐    ┌──────────────┐
│ Prompt PR  │ ─▶ │ Lint     │ ─▶ │ Eval    │ ─▶ │ Staging    │ ─▶ │ Prod Agent   │
│ in git     │    │ check    │    │ suite   │    │ deploy     │    │ Engine deploy│
└────────────┘    └──────────┘    └─────────┘    └────────────┘    └──────────────┘
                                       │
                                       ▼ (on failure)
                                   block merge
```

The eval suite is the only thing standing between a prompt change and production. Take it seriously. See `05-evaluation-and-guardrails.md`.

---

## Versioning Strategy

The prompt is the product. Version it:

- **Semantic versioning** on the prompt itself (`system.md` carries `# Version 1.4.2` in the first line as a comment that the model ignores).
- **Git tag** every prompt release.
- **Pin a version** in production if you need a frozen reviewer. Default to rolling with an eval gate.

Why pin: principal-SRE judgment style is a deliverable. If you change it, reviewers notice. Pinning prevents accidental regressions.

---

## Common Pitfalls

| Pitfall | Fix |
|---|---|
| `adk web` doesn't find the agent | Run it from `implementation/` (`adk web .`). If you wrap this in a Python package, the folder name must match the package and `__init__.py` must exist |
| `SkillToolset` import fails | You're on an older ADK. Upgrade: `pip install -U google-adk` — Skills landed in 1.4.0 |
| `output_schema` not respected | Gemini sometimes ignores schemas with deeply nested optional fields. Flatten the schema or use post-processing validation. |
| Agent calls `search_sre_corpus` on every review | Tool description is too permissive. Tighten to "use ONLY when grounding a critique requires citing source" |
| `nobl9_catalog_lookup` missing from tools | Set `NOBL9_CLIENT_ID` and `NOBL9_CLIENT_SECRET`. Restart the process after changing env. |
| Nobl9 429 on `/api/accessToken` | Reuse the cached JWT (1 hour). Do not mint a token per tool call. |
| Cost is 3x expected | Check whether structured output is being requested every turn. Set `output_schema` to None for follow-up turns where the verdict is already rendered. |
| Docs aren't ingesting into the datastore | Check the GCS bucket region matches the datastore region, and the agent's service account has `roles/storage.objectViewer` on the bucket |

---

## Next: read `05-evaluation-and-guardrails.md` for the eval framework that keeps this product trustworthy in production.
