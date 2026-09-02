# Implementation — ADK Reference Agent

Runnable reference for the SLO Review Board Agent.

- **Gemini Enterprise Agent Studio:** paste `prompts/system.md` into **Details → Instructions**; follow `docs/03-implementation-agent-studio.md` (no code required for POC).
- **ADK / Agent Runtime:** use `agent.py` with `docs/04-implementation-adk-code-first.md` and `docs/05-evaluation-and-guardrails.md`.

## Contents

| Path | Purpose |
|------|---------|
| `agent.py` | ADK agent definition (tools, skills, structured verdict schema) |
| `nobl9_client.py` | Read-only Nobl9 REST client (token cache, Objects API, Status API v2) |
| `prompts/system.md` | Deployed system instruction (extracted from `docs/02-master-system-prompt.md`) |
| `prompts/vertical-*.md` | Optional prepends for `gxp`, `fedramp`, `pci` |
| `skills/*/SKILL.md` | ADK SkillToolset bodies |
| `evals/evals.json` | Golden eval set for regression testing |
| `tests/` | Mocked unit tests (Nobl9 catalog; no live org calls) |

## Prerequisites

- Google Cloud project with Vertex AI and Agent Engine APIs enabled
- Environment variables required by `agent.py` (see `docs/04` for full list):
  - `GOOGLE_CLOUD_PROJECT`
  - `SLO_REVIEW_DOCS_DATASTORE`
  - `SLO_REVIEW_SRE_CORPUS_DATASTORE`
  - Optional: `DEPLOYMENT_VERTICAL`
  - Optional Nobl9 catalog: `NOBL9_CLIENT_ID`, `NOBL9_CLIENT_SECRET`, `NOBL9_ORGANIZATION`, `NOBL9_URL`, `NOBL9_PROJECT`

## Local smoke test

```bash
cd implementation
export GOOGLE_CLOUD_PROJECT=your-project
# ... set remaining env vars per docs/04
python agent.py
```

Interactive UI: run `adk web .` from this directory after installing ADK.

## Deploy

```bash
adk deploy agent_engine --agent agent.agent --region us-central1
```

Adjust module path to match your packaging if you wrap this in a `slo_review_agent/` Python package per `docs/04`.

## Prompt changes

1. Edit `prompts/system.md` (or vertical files).
2. Keep `docs/02-master-system-prompt.md` in sync for documentation.
3. Run the eval suite in `docs/05` against `evals/evals.json` before promoting.

## Evals

```bash
# See docs/05 for the intended runner; it is specified but not shipped:
# python evals/run_evals.py --agent agent.agent --evalset evals/evals.json
```

Wire `evals/run_evals.py` when you add CI — `docs/05-evaluation-and-guardrails.md` and `specs/001-slo-review-board-agent/tasks.md` describe the expected gate.

Nobl9 catalog unit tests (mocked; no live API):

```bash
python -m unittest discover -s implementation/tests -v
```
