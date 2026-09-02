# Contributing

This repo is a reference implementation. The system prompt and eval set are the product; treat them like production code.

## Before you open a PR

1. Keep `.specify/memory/constitution.md` as the source of truth for review principles. Prompt changes that weaken a principle will be rejected.
2. If you change `implementation/prompts/` or a vertical prepend, update `docs/02-master-system-prompt.md` to match and add or adjust cases in `implementation/evals/evals.json`.
3. Do not commit `.env`, credentials, or real SLO documents. Samples and eval cases must stay fictional.

## Suggested PR shape

- **Prompt / principle change:** constitution bump (if needed) + prompt + eval case + short rationale.
- **Tooling change:** `implementation/agent.py` plus the matching deploy guide (`docs/03` or `docs/04`).
- **Docs-only:** fine as a small PR.

## Local smoke check

```bash
cd implementation
pip install -r requirements.txt
export GOOGLE_CLOUD_PROJECT=your-project
export SLO_REVIEW_DOCS_DATASTORE=slo-review-docs
export SLO_REVIEW_SRE_CORPUS_DATASTORE=slo-review-sre-corpus
python agent.py
```

The eval runner described in `docs/05-evaluation-and-guardrails.md` is the intended CI gate. Wire it to your ADK runtime before treating prompt changes as production-ready.
