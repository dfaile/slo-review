# Documentation — SLO Review Board Agent

Architecture, deploy guides, system prompt, evaluation, and Spec Kit integration. Start with the [root README](../README.md). Versions live in [VERSION](../VERSION).

---

## Guide index

| Guide | Purpose |
|-------|---------|
| [01-architecture-and-design.md](01-architecture-and-design.md) | Stack rationale, model selection, deployment paths |
| [02-master-system-prompt.md](02-master-system-prompt.md) | Canonical system prompt (source for `implementation/prompts/system.md`) |
| [03-implementation-agent-studio.md](03-implementation-agent-studio.md) | Gemini Enterprise Agent Studio: Flow, Details, Preview, deploy |
| [04-implementation-adk-code-first.md](04-implementation-adk-code-first.md) | ADK Python deployment to Agent Engine |
| [05-evaluation-and-guardrails.md](05-evaluation-and-guardrails.md) | Eval framework, regression testing, guardrails |
| [07-speckit-integration.md](07-speckit-integration.md) | Spec Kit SDD + extension integration |

---

## Related directories

| Directory | Purpose |
|-----------|---------|
| `../implementation/` | `agent.py`, prompts, skills, `evals/evals.json` |
| `../.specify/memory/constitution.md` | Governing principles |
| `../specs/001-slo-review-board-agent/` | Spec Kit spec, plan, tasks, research |
| `../speckit-extension/speckit-slo-review/` | `/speckit.slo-review` extension |

---

## Suggested reading order

**Agent Studio POC:** 01 → 03 → Preview with `../samples/case-03-*` → deploy → record the `reasoningEngines/...` resource name.

**ADK production:** 01 → 04 → 05. Calibrate tone with eval case `case-03-rejected-majority-cause-based`.
