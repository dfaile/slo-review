# SLO Review Board Agent

A principal-SRE review agent for SLO implementation proposals. It reads an SLO Discovery document plus an Implementation Guide and returns a verdicted approval paper: Approved, Approved with Revisions, or Rejected — Recommend Rescope.

Built for [Gemini Enterprise Agent Platform](https://cloud.google.com/gemini) (Agent Studio or ADK + Agent Engine). Optional in-editor reviews via a [GitHub Spec Kit](https://github.com/github/spec-kit) extension.

This is a **reference implementation**, not a hosted product. You deploy it in your own Google Cloud project.

## What it does

The agent applies a fixed review framework (symptoms over causes, SLO count discipline, grounded targets, dependency ceiling) and will not soften a verdict under pressure. New facts can change the paper; arguing with it cannot.

## Layout

```
slo-review/
├── README.md
├── LICENSE                      Apache-2.0
├── VERSION                      component versions
├── .specify/memory/constitution.md
├── specs/001-slo-review-board-agent/
├── docs/                        architecture, deploy, evals, Spec Kit
├── implementation/              ADK agent, prompts, skills, evals
├── samples/                     Markdown pairs for Agent Studio Preview
└── speckit-extension/speckit-slo-review/
```

## Who this is for

| Role | Start with |
|------|------------|
| Platform engineer deploying the agent | [`docs/01-architecture-and-design.md`](docs/01-architecture-and-design.md) → [`docs/03`](docs/03-implementation-agent-studio.md) or [`docs/04`](docs/04-implementation-adk-code-first.md) |
| Principal SRE / program owner | [`.specify/memory/constitution.md`](.specify/memory/constitution.md) + [`specs/001-slo-review-board-agent/spec.md`](specs/001-slo-review-board-agent/spec.md) |
| Developers reviewing SLOs in the IDE | [`speckit-extension/speckit-slo-review/README.md`](speckit-extension/speckit-slo-review/README.md) |

## Quick start

**POC (Agent Studio, ~1 day):**

1. Read [`docs/01-architecture-and-design.md`](docs/01-architecture-and-design.md)
2. Follow [`docs/03-implementation-agent-studio.md`](docs/03-implementation-agent-studio.md)
3. Test in Studio Preview with `samples/case-03-*`, then `implementation/evals/evals.json`

**Production (ADK + Agent Engine):**

1. Copy [`.env.example`](.env.example) to `.env` and fill in your project and datastore IDs
2. Read [`implementation/README.md`](implementation/README.md)
3. Follow [`docs/04-implementation-adk-code-first.md`](docs/04-implementation-adk-code-first.md)
4. Gate prompt changes with [`docs/05-evaluation-and-guardrails.md`](docs/05-evaluation-and-guardrails.md)

**In-editor preview reviews (Spec Kit):**

```bash
specify extension add ./speckit-extension/speckit-slo-review
```

Then: `/speckit.slo-review discovery.md impl-guide.md`

Details: [`speckit-extension/speckit-slo-review/README.md`](speckit-extension/speckit-slo-review/README.md) and [`docs/07-speckit-integration.md`](docs/07-speckit-integration.md).

## Two ways to use it

| Path | Audience | Artifact |
|------|----------|----------|
| **Deployed agent** | SRE platform, compliance, review boards | Vertex AI Agent Engine + `implementation/` |
| **Spec Kit extension** | Product engineers in a PR workflow | `speckit-extension/speckit-slo-review/` |

Preview reviews (local coding agent) are not audit records. Engine-mode reviews against a deployed Agent Engine endpoint are.

## Status

Shipped as a complete **prompt + skills + eval-case** package with a runnable ADK reference agent and an optional read-only Nobl9 catalog lookup (registered when `NOBL9_CLIENT_ID` and `NOBL9_CLIENT_SECRET` are set). Not yet shipped: a CI eval runner (`docs/05` specifies it).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).

The review framework is derived from the [Google SRE Book](https://sre.google/sre-book/table-of-contents/) and [SRE Workbook](https://sre.google/workbook/table-of-contents/) (CC BY-NC-ND 4.0). This repo does not redistribute book text verbatim; citation skill content must stay within that license.

The Spec Kit extension is also Apache-2.0 in this repository (the extension manifest historically said MIT; treat the repo license as canonical).
