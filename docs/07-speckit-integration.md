# 07 — Spec Kit Integration

This document explains how the SLO Review Board Agent integrates with GitHub Spec Kit, the open-source toolkit for Spec-Driven Development (SDD). Read this if you use Spec Kit for agent development or want developers to invoke SLO review from inside Spec Kit-enabled coding agents.

Two integration paths ship together. Use Path 1 to maintain the agent; use Path 2 to invoke reviews from the IDE. Use both if you do both.

---

## Background — What Spec Kit Is

Spec Kit (`github/spec-kit`) is GitHub's open-source toolkit for Spec-Driven Development. The methodology flips traditional development: instead of code-first, specifications become the executable source of truth that AI coding agents implement against. The workflow runs in phases, each backed by a slash command in your coding agent:

```
/speckit.constitution   →  Establish project governing principles (.specify/memory/constitution.md)
/speckit.specify        →  Describe WHAT to build, success criteria (specs/NNN-feature/spec.md)
/speckit.clarify        →  Resolve under-specified areas
/speckit.plan           →  Tech stack + architecture (specs/NNN-feature/plan.md)
/speckit.tasks          →  Ordered task breakdown (specs/NNN-feature/tasks.md)
/speckit.implement      →  Execute the tasks
```

Spec Kit is agent-agnostic: works with Claude Code, GitHub Copilot, Gemini CLI, Codex CLI, Cursor, and 30+ other coding agents. Extensions add new commands; presets override existing command templates to enforce organizational standards. As of v0.9.1 (June 2026), the catalog has 70+ community-contributed extensions.

---

## Why This Maps Cleanly to the SLO Review Agent

Two reasons.

**First**, the agent's framework is exactly the kind of thing Spec Kit's constitution concept was designed for. "Symptoms over causes, dependency ceiling, target validity, SLO count discipline" are durable principles that must constrain every iteration of the agent and every review the agent renders. Encoding them as a Spec Kit constitution makes them first-class artifacts the engineering team can reason about — and that any Spec Kit workflow on the project automatically references.

**Second**, the agent itself is a code project (Python, prompts, evals, configs). Its features (new vertical prepends, new tools, new eval categories) follow a natural spec → plan → tasks → implement lifecycle.

There's one honest caveat: Spec Kit's primary design target is coding agents working on conventional code projects. Using SDD to develop an AI agent is a slight stretch. The fit is good — not perfect.

---

## Path 1 — Maintain the Agent via Spec-Driven Development

### What ships in this repo

```
slo-review/
├── .specify/
│   └── memory/
│       └── constitution.md                   ← The framework as durable principles
└── specs/
    └── 001-slo-review-board-agent/
        ├── spec.md                           ← WHAT the agent does + success criteria
        ├── plan.md                           ← HOW it's built (tech stack, architecture)
        ├── tasks.md                          ← Ordered task breakdown
        └── research.md                       ← Research informing plan choices
```

### How to iterate on the agent

Use the familiar SDD workflow from this repo:

```bash
# In the slo-review/ directory, inside a Spec Kit-enabled coding agent
cd slo-review

# If amending principles (rare):
/speckit.constitution Add a seventh principle: every SLO must have an alert
                       policy attached before deployment
# → Bumps constitution version, updates .specify/memory/constitution.md

# Adding a new vertical prepend (most common iteration):
/speckit.specify Add a new vertical prepend for HIPAA-regulated services
                  emphasizing PHI handling and breach-notification SLOs
# → Creates specs/002-vertical-hipaa/spec.md

/speckit.clarify
# → Resolves ambiguities by asking targeted questions

/speckit.plan
# → Creates specs/002-vertical-hipaa/plan.md

/speckit.tasks
# → Creates specs/002-vertical-hipaa/tasks.md

/speckit.implement
# → Adds prompts/vertical-hipaa.md, updates agent.py, adds eval cases,
#   runs eval suite, blocks if anything regresses
```

The constitution acts as the binding standard: `/speckit.plan` and `/speckit.implement` will refuse to produce work that violates a principle in the constitution. Adding a vertical that softens the dependency-ceiling test, for example, would fail the compliance check.

This is useful in three ways:

1. **Version-controlled prompt evolution.** Every prompt change is a PR against `specs/`, reviewed against the constitution, gated on the eval suite. Drift is impossible without explicit version bumps.
2. **Onboarding new engineers.** A new engineer can read the constitution and spec in under an hour and understand both what the agent does and what bounds its behavior.
3. **Audit trail.** For regulated deployments, the constitution + spec + plan + tasks artifacts are evidence that the AI tool's behavior is governed and reviewed.

---

## Path 2 — Spec Kit Extension for In-Editor SLO Review

### What ships

```
slo-review/
└── speckit-extension/
    └── speckit-slo-review/
        ├── extension.yaml                    ← Manifest declaring the slash command
        ├── README.md                         ← Install + usage for end users
        └── templates/
            └── commands/
                └── slo-review.md             ← Slash command template
```

### How to install it

From any Spec Kit-enabled project (not just this repo):

```bash
# Once we publish to the Spec Kit catalog:
specify extension add speckit-slo-review

# During pilot, install directly from a path:
specify extension add /path/to/slo-review/speckit-extension/speckit-slo-review
```

This writes the slash command template into the appropriate agent directories:

- Claude Code: `.claude/commands/speckit.slo-review.md`
- GitHub Copilot: `.github/prompts/speckit.slo-review.prompt.md`
- Gemini CLI: `.gemini/commands/speckit.slo-review.toml`
- Codex CLI (skills mode): `.codex/skills/speckit-slo-review/`

### How developers use it

#### Preview mode (default)

```
/speckit.slo-review discovery/checkout-service.md slo-configs/checkout-service/impl-guide.md
```

The developer's local coding agent (Claude Code, Copilot, etc.) reads both files, applies the framework bundled in the slash command template, renders a preview review paper, and saves it to `./slo-reviews/checkout-service-2026-06-03-preview.md`.

Preview reviews carry the prefix **"PREVIEW REVIEW — not for audit / sign-off"**. They're fast, free (no Agent Engine cost), and intended for self-review during PR work.

#### Engine mode (auditable)

```
/speckit.slo-review discovery/checkout-service.md \
                    slo-configs/checkout-service/impl-guide.md \
                    --mode engine
```

The slash command calls the deployed Vertex AI Agent Engine endpoint and streams back the official review. Set `SLO_REVIEW_AGENT_ENGINE_RESOURCE` to the deployed engine resource name.

Engine reviews are auditable (logged, identity-attributed, output-schema-validated) and intended for sign-off. Each engine-mode review costs ~$0.14 per the cost model in `01-architecture-and-design.md`.

#### Vertical context

```
/speckit.slo-review discovery/clinical-trials-api.md \
                    slo-configs/clinical-trials-api/impl-guide.md \
                    --vertical gxp
```

Applies the GxP vertical prepend on top of the base framework. Available verticals: `horizontal` (default), `gxp`, `fedramp`, `pci`.

### Why this surface exists

Developers stay in their coding agent. They type a slash command and get a review — no separate web app.

1. **Self-review during PR work.** Engineers fix obvious problems (cause-based SLIs, ungrounded targets) before submitting for human review.
2. **Gating in `/speckit.implement`.** If you author SLO configs with Spec Kit, wire the review into the implementation pipeline as a task that blocks on a Rejected verdict.
3. **Preview vs engine.** Drafts run locally (no Agent Engine cost). Reviews of record go through the deployed endpoint (~$0.14 per the cost model in `01-architecture-and-design.md`).

---

## How Path 1 and Path 2 Work Together

These are not competing offerings; they serve different audiences in the same organization.

```
┌─────────────────────────────────────────────────────────────────────┐
│ Organization                                                        │
│                                                                     │
│   ┌────────────────────────┐         ┌────────────────────────┐     │
│   │ Platform / SRE         │         │ Product engineering    │     │
│   │ engineering team       │         │ teams (40+ services)   │     │
│   │ (maintains the agent)  │         │ (use the agent)        │     │
│   └───────────┬────────────┘         └───────────┬────────────┘     │
│               │                                  │                  │
│               ▼                                  ▼                  │
│   ┌────────────────────────┐         ┌────────────────────────┐     │
│   │ PATH 1                 │         │ PATH 2                 │     │
│   │ .specify/ + specs/     │         │ /speckit.slo-review    │     │
│   │ Iterate the agent      │         │ slash command          │     │
│   │ via SDD                │         │ in their coding agent  │     │
│   └───────────┬────────────┘         └───────────┬────────────┘     │
│               │                                  │                  │
│               └────────┬─────────────────────────┘                  │
│                        ▼                                            │
│              ┌─────────────────────┐                                │
│              │ Deployed SLO Review │                                │
│              │ Board Agent on      │                                │
│              │ Agent Engine        │                                │
│              └─────────────────────┘                                │
└─────────────────────────────────────────────────────────────────────┘
```

The platform/SRE team owns the agent's behavior — they touch Path 1, they amend the constitution, they iterate prompts under spec-driven discipline.

The product engineering teams consume the agent — they touch Path 2, they invoke `/speckit.slo-review` during PR work, they get verdicts.

Both audiences end up at the same deployed Agent Engine endpoint. The Path 1 work changes what that endpoint does; the Path 2 work uses it.

---

## Rollout when Spec Kit is in play

### Week 1

- After deploying the agent, keep `.specify/` and `specs/` in this repo (or copy them next to the deployed config).
- Joint review of the constitution with the principal SRE. Capture environment-specific additions as a local constitution amendment.

### Week 2

- Install the `speckit-slo-review` extension in one pilot team's coding agent (Claude Code, Copilot, Cursor, or Gemini CLI).
- Run preview reviews on three real SLO proposals. Measure verdict agreement with the principal SRE.

### Week 3

- Roll the extension out to additional teams.
- Optionally wire engine-mode `/speckit.slo-review` into CI as a quality gate on PRs touching SLO config.

### Week 4

- Train the platform team on amending the constitution, adding a vertical prepend via `/speckit.specify`, and running the eval gate locally.

---

## Versioning Considerations

The agent has three independently versioned artifacts that move together:

| Artifact | Version | What changes |
|---|---|---|
| Constitution | `1.0.0` (semver) | Principles added/removed/refined |
| System prompt | matches constitution | Reflects principle changes |
| Extension | `0.1.0` (semver) | Slash command behavior, supported agents |

Pin all three in production if you need a frozen reviewer; otherwise roll them together behind the eval gate.

When Spec Kit itself releases a major version (currently 0.9.x), validate the extension still installs cleanly and update `spec_kit_min_version` in `extension.yaml`.

---

## Why this is useful

1. **You already use Spec Kit for AI agents.** Same workflow, same artifacts, same mental model.
2. **Developers live in Claude Code / Copilot / Cursor.** Path 2 means SLO review is one slash command away from where they already work.
3. **You have an SDD initiative.** This repo is a reference for using SDD to develop an AI agent, not only application code.

If none of those apply, the Spec Kit integration is still useful (versioned prompt evolution, extension surface) but is not the lead value.

---

## What you get

- A deployed AI reviewer that applies a known framework consistently across every SLO proposal
- A constitution the engineering team can review, amend (with discipline), and reference in audit conversations
- A slash command developers can invoke from inside their existing coding agents
- A versioned, eval-gated process for evolving the agent's behavior over time
- The option to pin to a specific version if you want stability over bleeding-edge

What you don't get:

- A code-writing agent (Spec Kit's primary use case is for coding agents working on code; this is an SLO-reviewing agent that happens to be developed under SDD)
- A replacement for principal SREs (it surfaces obvious findings so they can spend their time on the hard cases)
- Auto-modification of SLO configs (review only; you decide what to change)

---

## Reference Files

| File | Purpose |
|---|---|
| `.specify/memory/constitution.md` | The framework as durable principles |
| `specs/001-slo-review-board-agent/spec.md` | What the agent does + success criteria |
| `specs/001-slo-review-board-agent/plan.md` | Tech stack + architecture |
| `specs/001-slo-review-board-agent/tasks.md` | Ordered implementation breakdown |
| `specs/001-slo-review-board-agent/research.md` | Research informing plan decisions |
| `speckit-extension/speckit-slo-review/extension.yaml` | Extension manifest |
| `speckit-extension/speckit-slo-review/README.md` | Install + usage guide |
| `speckit-extension/speckit-slo-review/templates/commands/slo-review.md` | Slash command template |
| `implementation/agent.py` | ADK reference agent |
| `implementation/evals/evals.json` | Golden eval set |
| `docs/01`–`05`, `docs/07` | Deployment and operations guides |
| `VERSION` | Package and component version manifest |

---

## Next

1. Walk the principal SRE through `.specify/memory/constitution.md`
2. Pilot the `speckit-slo-review` extension with one team
3. Expand based on adoption
4. Gate prompt changes with `05-evaluation-and-guardrails.md`
