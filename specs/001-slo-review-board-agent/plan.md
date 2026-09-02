# Plan — SLO Review Board Agent

**Feature ID**: 001-slo-review-board-agent
**Spec**: `specs/001-slo-review-board-agent/spec.md`
**Constitution version**: 1.0.0

> This plan translates the spec into architectural decisions. Implementation steps live in `tasks.md`. Research that informs these choices is in `research.md`.

---

## Tech Stack Decisions

| Layer | Choice | Justification |
|---|---|---|
| Foundation model | Gemini 3.1 Pro | Long-context reasoning required to hold discovery + impl guide together; principal-SRE judgment requires Pro-tier reasoning |
| Agent framework | Google Agent Development Kit (ADK), Python | Native Skill support via `SkillToolset` lets the existing `SKILL.md` port with minimal restructuring; deploys natively to Agent Engine |
| Runtime | Vertex AI Agent Engine | Managed runtime within Gemini Enterprise Agent Platform; removes operational burden, provides identity/governance/audit out of the box |
| Grounding | Vertex AI Search | Tenant-private datastores per Article III, Principle 3.3; first-class integration with ADK |
| Document ingestion | Cloud Storage | Doc pairs land in a CMEK-encrypted bucket; agent reads via service account |
| Optional integrations | Nobl9 API (optional), Slack, GitHub Actions, ServiceNow | Surface options based on where developers already live |
| Eval framework | Pytest + custom eval runner | Smoke, verdict-accuracy, verdict-stability suites; CI-gated per Principle 3.2 |

Alternatives considered and rejected: see `research.md`.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│ Caller-facing surface (Slack / Teams / Web / API / Spec Kit ext)  │
└──────────────────────────────┬────────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────────┐
│ Vertex AI Agent Engine (deployed reasoning engine)                │
│                                                                   │
│   ┌─────────────────────────────────────────────────────┐         │
│   │ SLO Review Agent (ADK Agent)                        │         │
│   │   Model: gemini-3.1-pro, temp 0.2                   │         │
│   │   System instruction: prompts/system.md +           │         │
│   │     optional vertical prepend                       │         │
│   │   Output schema: ReviewVerdict (pydantic)           │         │
│   └────┬────────────────────────────────────────────────┘         │
│        │                                                          │
│   ┌────▼────────────────────────────────────────────────┐         │
│   │ SkillToolset (3-tier loading)                       │         │
│   │   L1 list_skills   - metadata only                  │         │
│   │   L2 load_skill    - slo-approval-review.md         │         │
│   │   L3 load_resource - SRE-Book citations             │         │
│   └─────────────────────────────────────────────────────┘         │
│                                                                   │
│   ┌─────────────────────────────────────────────────────┐         │
│   │ Tools                                               │         │
│   │   ingest_documents  - GCS prefix → discovery+guide  │         │
│   │   search_sre_corpus - Vertex AI Search on framework │         │
│   │   nobl9_catalog     - Enterprise tier only          │         │
│   └─────────────────────────────────────────────────────┘         │
└───────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│ Tenant-private storage (CMEK)                                     │
│   GCS bucket: discovery + impl guide uploads                      │
│   Vertex AI Search datastore #1: review documents                 │
│   Vertex AI Search datastore #2: SRE corpus + org standards       │
└───────────────────────────────────────────────────────────────────┘
```

---

## Component Design

### Component 1 — System Instruction

Located at `implementation/prompts/system.md`. Loaded at agent construction time. Approximately 4,800 tokens. Optional vertical prepend (`implementation/prompts/vertical-{gxp|fedramp|pci}.md`) is prepended at runtime based on `DEPLOYMENT_VERTICAL` env var.

**Design constraints (from Constitution Article II):**
- Mandatory section order
- Verdict-in-first-sentence
- Adversarial-input clause (Section 7 of prompt)
- Guardrails clause (Section 8 of prompt)

### Component 2 — SkillToolset

Two skills, both shipped:

- **`slo-approval-review`** — full framework, loaded on every invocation
- **`sre-principles-citation`** — on-demand citations from SRE Book, loaded only when grounding is needed (saves ~5k tokens per routine invocation)

### Component 3 — Tools

| Tool | Inputs | Outputs | Used when |
|---|---|---|---|
| `ingest_documents` | GCS prefix | `{discovery: str, implementation_guide: str}` | Every invocation |
| `search_sre_corpus` | query string | List of relevant passages | When agent needs to ground a critique |
| `nobl9_catalog_lookup` | service name | Existing SLO catalog for the service | Enterprise tier; when customer asks about overlap with deployed SLOs |

### Component 4 — Structured Output

`ReviewVerdict` pydantic model emitted alongside the Markdown paper. Lets downstream consumers (Slack notifications, ServiceNow tickets, dashboards) consume the verdict programmatically without parsing Markdown.

Fields: `verdict`, `service_name`, `slo_evaluations[]`, `gaps[]`, `excess[]`, `sign_off_conditions[]`, `full_paper_markdown`.

### Component 5 — Eval Suite

Three suites (see `05-evaluation-and-guardrails.md`):
- **Smoke**: agent loads, instruction present, tools registered, skills loaded. <10 s, every commit.
- **Verdict accuracy**: 6 golden cases × 3 runs each. Pass-threshold 2-of-3 per case.
- **Verdict stability**: pressure-only adversarial follow-ups must not move verdict; new-information follow-ups must move verdict to expected new value.

---

## Deployment Topology

Two deployment paths, both terminating at the same Agent Engine artifact:

### Path A — Agent Studio (low-code)

Gemini Enterprise Agent Studio (Flow + Details + Preview). Setup in under an hour. Best for first POCs and console-based builders.

### Path B — ADK (code-first)

Python module, `adk deploy agent_engine`. CI-gated by eval suite. Best for production and this repo's reference deployment.

Both paths are documented in `03-implementation-agent-studio.md` and `04-implementation-adk-code-first.md` respectively.

---

## Spec Kit Integration

This project is itself maintained under Spec-Driven Development. The constitution governs both agent behavior and engineering practice. New features (new vertical prepend, new tool, new eval case) follow the full SDD workflow:

```
/speckit.constitution    # only if amending principles
/speckit.specify         # specify the new feature
/speckit.clarify         # resolve open questions
/speckit.plan            # produce the architectural impact
/speckit.tasks           # break into ordered tasks
/speckit.implement       # execute with eval gate
```

Additionally, the project ships a Spec Kit Extension (`speckit-extension/speckit-slo-review/`) that adds `/speckit.slo-review` as a slash command for end users. See `docs/07-speckit-integration.md`.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Gemini 3.1 Pro deprecated | Medium (Google rapid iteration) | High | Eval suite re-runs against successor model; system prompt is portable |
| Verdict drift after prompt changes | Medium | Critical | Stability eval suite is a release gate per Principle 3.2 |
| ADK API changes (Skill, SkillToolset) | Medium (pre-1.0 SDK) | Medium | Pin `google-adk` version; test on minor bumps; abstract skill loading behind a stable interface |
| Regulated environment rejects external model calls | Low | Medium | Path B supports VPC-resident Agent Engine; Customer-Managed Encryption Keys; data residency pinning |
| Vertex AI Search rebrand or migration | Low | Low | Grounding interface is abstracted in `search_sre_corpus` tool; swap implementation if needed |
| Spec Kit extension format changes | Medium (rapid pre-1.0 evolution) | Low | Extension is one of several integration surfaces; not a single point of failure |

---

## Constitution Compliance Check

This plan has been verified against `.specify/memory/constitution.md` v1.0.0:

- [x] Article I — six review principles reflected in System Instruction component
- [x] Article II — verdict behavior enforced via system prompt sections 5–7 and stability eval
- [x] Article III, 3.1 — system prompt versioned in `prompts/system.md` header
- [x] Article III, 3.2 — eval suite is documented as release gate
- [x] Article III, 3.3 — per-tenant datastores, CMEK called out in storage layer
- [x] Article III, 3.4 — vertical prepends are extend-only by design
- [x] Article III, 3.5 — SkillToolset is the elaboration mechanism, not prompt patches

No conflicts identified. Ready for `/speckit.tasks`.
