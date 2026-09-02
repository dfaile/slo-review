# Tasks — SLO Review Board Agent

**Feature ID**: 001-slo-review-board-agent
**Plan**: `specs/001-slo-review-board-agent/plan.md`
**Constitution version**: 1.0.0

> Tasks are ordered by dependency. `[P]` marks tasks that can run in parallel. Each task lists the file(s) it touches and how completion is verified.

---

## Phase 0 — Foundation (one-time, complete)

### T0.1 [P] — Author the constitution
- **File**: `.specify/memory/constitution.md`
- **Verify**: Constitution exists, version 1.0.0, six review principles + five engineering principles articulated
- **Status**: ✅ Done in v1.0

### T0.2 [P] — Author the spec
- **File**: `specs/001-slo-review-board-agent/spec.md`
- **Verify**: Five user stories, success criteria, out-of-scope statements, constitution compliance check
- **Status**: ✅ Done in v1.0

### T0.3 — Author the plan (depends on T0.1, T0.2)
- **File**: `specs/001-slo-review-board-agent/plan.md`
- **Verify**: Tech stack documented, architecture diagram, component design, risk register
- **Status**: ✅ Done in v1.0

---

## Phase 1 — Core Prompt Engineering (sequential — prompt is a single artifact)

### T1.1 — Draft the master system prompt
- **File**: `prompts/system.md`
- **Verify**: Token count between 4,500 and 5,500; nine sections in mandated order; no emojis, no hedging language; sections 7 and 8 explicit
- **Constitution refs**: Article I, Article II

### T1.2 — Draft vertical prepends [P after T1.1]
- **Files**: `prompts/vertical-gxp.md`, `prompts/vertical-fedramp.md`, `prompts/vertical-pci.md`
- **Verify**: Each prepend extends (does not weaken) the base framework per Principle 3.4
- **Constitution refs**: Article III, Principle 3.4

### T1.3 — Author the two skills
- **Files**: `skills/slo-approval-review/SKILL.md`, `skills/sre-principles-citation/SKILL.md`
- **Verify**: Skills load via ADK's `SkillToolset`; `list_skills` returns both
- **Constitution refs**: Article III, Principle 3.5

---

## Phase 2 — Tooling

### T2.1 — Implement `ingest_documents` tool
- **File**: `agent.py` (function definition)
- **Verify**: Function fetches discovery + implementation guide from a GCS prefix; handles missing-file cases gracefully

### T2.2 [P] — Implement `search_sre_corpus` tool
- **File**: `agent.py`
- **Verify**: Function queries Vertex AI Search datastore; returns list of passages with titles, excerpts, source URIs

### T2.3 [P] — Implement `nobl9_catalog_lookup` tool (Enterprise tier only)
- **File**: `agent.py`
- **Verify**: Function returns existing SLO catalog from Nobl9 API; gracefully no-ops on standard tier

### T2.4 — Wire tools into agent
- **File**: `agent.py`
- **Depends on**: T2.1, T2.2, T2.3
- **Verify**: `agent.tools` contains the right set based on `DEPLOYMENT_TIER` env var

---

## Phase 3 — Structured Output

### T3.1 — Define `ReviewVerdict` schema
- **File**: `agent.py` (pydantic models)
- **Verify**: Includes verdict, service_name, slo_evaluations[], gaps[], excess[], sign_off_conditions[], full_paper_markdown

### T3.2 — Configure agent to emit structured output
- **File**: `agent.py`
- **Depends on**: T3.1
- **Verify**: `Agent(output_schema=ReviewVerdict, ...)` is set

---

## Phase 4 — Provisioning

### T4.1 [P] — Provision per-tenant GCS bucket with CMEK
- **Where**: Customer's GCP project
- **Verify**: Bucket exists in customer-pinned region, CMEK enabled, agent service account has `roles/storage.objectViewer`
- **Constitution refs**: Article III, Principle 3.3

### T4.2 [P] — Provision Vertex AI Search datastore for customer documents
- **Where**: Customer's GCP project
- **Verify**: Datastore exists, linked to customer GCS bucket, incremental import mode

### T4.3 [P] — Provision Vertex AI Search datastore for SRE corpus
- **Where**: Customer's GCP project
- **Verify**: Datastore exists, populated from the SRE corpus bucket
- **Constitution refs**: Article III, Principle 3.3 (no cross-tenant retrieval — corpus is replicated, not shared)

### T4.4 — Configure environment variables
- **Files**: `.env.production`, Secret Manager entries
- **Depends on**: T4.1, T4.2, T4.3
- **Verify**: All required env vars set; secrets are in Secret Manager, not `.env`

---

## Phase 5 — Eval Suite (Release Gate)

### T5.1 — Smoke tests
- **File**: `tests/test_agent_smoke.py`
- **Verify**: Tests run in <10 s; cover agent loads, system instruction present, tools registered, skills loaded
- **Constitution refs**: Article III, Principle 3.2

### T5.2 — Golden eval set
- **File**: `evals/evals.json`
- **Verify**: 6 cases minimum; 2 per verdict type; required_findings and prohibited_findings populated
- **Status**: ✅ Shipped at v1.0

### T5.3 — Verdict accuracy runner
- **File**: `evals/run_evals.py`
- **Depends on**: T5.2
- **Verify**: Runs each case 3 times; 2-of-3 pass threshold; checks first-sentence-verdict, length cap, no emojis

### T5.4 — Verdict stability runner
- **File**: `evals/run_evals.py` (same script, different mode)
- **Depends on**: T5.2
- **Verify**: Pressure follow-ups must not move verdict; new-information follow-ups must move verdict to expected new value
- **Constitution refs**: Article II, Principle 2.2 (most important eval in the suite)

### T5.5 — Wire eval suite into CI
- **File**: `.github/workflows/eval-gate.yml` (or equivalent)
- **Depends on**: T5.1, T5.3, T5.4
- **Verify**: Eval failures block PR merge to main; stability failures are unconditional blockers

---

## Phase 6 — Deployment

### T6.1 — Local smoke test
- **Command**: `adk web slo_review_agent`
- **Verify**: Web UI launches; agent responds; tool-call trace shows `ingest_documents` called before verdict rendered

### T6.2 — Staging deploy
- **Command**: `adk deploy agent_engine --agent slo_review_agent.agent --display-name "Staging — [Customer]"`
- **Depends on**: T5.5 passing
- **Verify**: Agent Engine resource exists; canary review on three known cases returns expected verdicts

### T6.3 — Production deploy
- **Command**: `adk deploy agent_engine --agent slo_review_agent.agent --display-name "Production — [Customer]"`
- **Depends on**: T6.2 canary passing
- **Verify**: Agent Engine endpoint reachable from customer's IAM-allowed identities; first three real-customer reviews validated by customer's principal SRE

---

## Phase 7 — Customer-Facing Surfaces

### T7.1 [P] — Slack integration
- **File**: `slack_integration/handler.py`
- **Verify**: `/slo-review <gcs-uri>` command works in customer's Slack workspace; review paper posts as Block Kit message

### T7.2 [P] — Spec Kit extension
- **Files**: `speckit-extension/speckit-slo-review/*`
- **Verify**: `specify extension add speckit-slo-review` installs cleanly; `/speckit.slo-review` slash command works in Claude Code, Copilot, and Gemini CLI

### T7.3 [P] — GitHub Action (optional)
- **File**: `.github/workflows/slo-review.yml` (in the SLO config repo)
- **Verify**: PR comment with review paper appears on every PR touching `slo-configs/**`

### T7.4 [P] — ServiceNow workflow (Enterprise tier only)
- **Verify**: Now Assist custom skill invokes Agent Engine endpoint; review attached to RITM record

---

## Phase 8 — Onboarding and Operations

### T8.1 — Rollout playbook
- **File**: `docs/07-speckit-integration.md` (rollout section) plus `docs/03` / `docs/04` checklists
- **Verify**: First three reviews validated by a principal SRE

### T8.2 — Observability dashboard
- **Where**: Looker Studio (or equivalent, org-owned)
- **Verify**: Five panels (latency, cost, verdict distribution, tool-call rate, satisfaction) populated from Agent Engine telemetry

### T8.3 — Quarterly review report
- **Cadence**: Quarterly
- **Verify**: Usage / verdict / cost report reviewed with the SRE program owner

---

## Constitution Compliance Check

This task plan has been verified against `.specify/memory/constitution.md` v1.0.0:

- [x] Article I — T1.1, T1.2, T1.3 implement the framework
- [x] Article II — T5.4 enforces verdict stability
- [x] Article III, 3.1 — T1.1 produces a versioned prompt
- [x] Article III, 3.2 — T5.5 makes eval a release gate
- [x] Article III, 3.3 — T4.1, T4.2, T4.3 enforce per-tenant storage
- [x] Article III, 3.4 — T1.2 verifies extend-only verticals
- [x] Article III, 3.5 — T1.3 uses skills, not prompt patches

No tasks identified as conflicting with the constitution. Ready for `/speckit.implement`.

---

## Notes for `/speckit.implement`

- Tasks in Phase 0 are documentation-only and complete.
- Phases 1–3 are sequential within themselves; some tasks within a phase can run in parallel where marked `[P]`.
- Phase 4 (provisioning) can begin in parallel with Phase 1 once tenancy is known.
- Phase 5 (eval suite) gates Phase 6 (deployment). No deploy proceeds without green evals.
- Phases 7 and 8 are customer-specific and can run in any order after Phase 6.

The agent has been implemented at v1.0 of this spec. Re-running `/speckit.implement` against this `tasks.md` would no-op on completed tasks and only execute tasks added by subsequent amendments.
