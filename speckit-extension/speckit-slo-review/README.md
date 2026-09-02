# speckit-slo-review

A [Spec Kit](https://github.com/github/spec-kit) extension that adds `/speckit.slo-review` as a slash command in your coding agent. Renders a principal-SRE approval review of an SLO Implementation Guide against an SLO Discovery document.

Counterpart to the deployed **SLO Review Board Agent** in the parent repo (`implementation/` + Vertex AI Agent Engine). Use this extension for in-editor preview reviews; use engine mode for auditable sign-off.

## Two operating modes

| Mode | Where the review runs | Use for |
|------|----------------------|---------|
| `preview` (default) | Local coding agent + bundled framework | PR self-review, pre-submission |
| `engine` | Vertex AI Agent Engine endpoint | Official sign-off, audit record |

Preview papers are prefixed **"PREVIEW REVIEW — not for audit / sign-off"**.

## Install

```bash
# From the Spec Kit catalog (once published)
specify extension add speckit-slo-review

# From this repository
specify extension add /path/to/slo-review/speckit-extension/speckit-slo-review
```

Installed locations (varies by agent):

- **Claude Code**: `.claude/commands/speckit.slo-review.md` or `.claude/skills/speckit-slo-review/`
- **GitHub Copilot**: `.github/prompts/speckit.slo-review.prompt.md`
- **Gemini CLI**: `.gemini/commands/speckit.slo-review.toml`
- **Codex CLI**: `.codex/skills/speckit-slo-review/`
- **Cursor**: skills or slash-command mode

## Configure (engine mode)

```bash
export SLO_REVIEW_AGENT_ENGINE_RESOURCE="projects/PROJECT/locations/REGION/reasoningEngines/ENGINE_ID"
gcloud auth application-default login
```

## Use

```bash
/speckit.slo-review discovery/checkout.md slo-configs/checkout/impl-guide.md

/speckit.slo-review discovery/api.md slo-configs/api/impl-guide.md --vertical gxp

/speckit.slo-review discovery/checkout.md slo-configs/checkout/impl-guide.md --mode engine
```

Verticals: `horizontal` (default), `gxp`, `fedramp`, `pci`.

Reviews save under `./slo-reviews/[service]-[date]-preview.md` (preview) or without the preview prefix (engine).

## Constitution

This extension applies the package constitution at `../../.specify/memory/constitution.md`. Optionally copy it into the consuming project:

```bash
cp ../../.specify/memory/constitution.md .specify/memory/slo-constitution.md
```

## Uninstall

```bash
specify extension remove speckit-slo-review
```

Does not remove saved papers under `./slo-reviews/`.

## Compatibility

- Spec Kit 0.9.0+
- Apache-2.0 (same as the parent repository). Framework derived from Google SRE Book/Workbook (CC BY-NC-ND 4.0)
