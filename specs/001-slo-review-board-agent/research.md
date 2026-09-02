# Research — SLO Review Board Agent

**Feature ID**: 001-slo-review-board-agent
**Plan**: `specs/001-slo-review-board-agent/plan.md`

> This document captures the research that informed the technology and architecture choices in `plan.md`. Future amendments to the plan should reference and update this file rather than re-deriving decisions.

---

## R-1: Choice of foundation model

### Question
Which foundation model should power the agent's principal-SRE reasoning?

### Considered

| Model | Strengths | Weaknesses |
|---|---|---|
| Gemini 3.1 Pro | Frontier reasoning, 1M-token context, native to Google Cloud / Agent Engine, no cross-cloud egress | Verdict tone calibration takes more few-shot examples than Claude |
| Gemini 3.1 Flash | 3x cheaper, 2x faster | Drops noticeable verdict quality on ambiguous "Approved with Revisions" cases |
| Claude Opus 4.7 (via Model Garden) | Strongest verdict tone out-of-the-box; minimal few-shot needed | Higher per-token cost; cross-tenant data flow considerations for some customers |
| GPT-class via direct API | Strong reasoning | No native Agent Engine integration; you carry identity/governance/audit |
| Open-source (Llama, Mistral) | Self-hosted; no per-token cost | Reasoning quality not at the level needed for principal-SRE judgment on technical correctness as of 2026-Q2 |

### Decision

**Primary**: Gemini 3.1 Pro. Best balance of reasoning quality, platform integration, and cost. Native to the agent runtime.

**Optional upgrade**: Claude Opus 4.7 via Model Garden for customers willing to pay ~20% premium for stronger out-of-the-box verdict tone.

**Reconsider when**: Gemini 4 ships, or open-source reasoning closes the gap with frontier models on technical-judgment benchmarks (estimated 12–18 months out from June 2026).

---

## R-2: Agent framework

### Question
Which framework should structure the agent's tool-calling and skill loading?

### Considered

| Framework | Notes |
|---|---|
| Google ADK (Agent Development Kit) | Open source, agent-native, deploys to Agent Engine; Skill support landed in 1.4.0 |
| LangGraph | Mature, vendor-neutral, but carries its own runtime burden |
| LlamaIndex Agents | Strong for RAG-heavy use cases; weaker for tool-rich agents |
| Roll our own | Forfeits all the agent-platform features (identity, observability, skill loading) we'd want anyway |

### Decision

**ADK**. The native Skill support (`SkillToolset` with three-tier loading: `list_skills`, `load_skill`, `load_skill_resource`) maps cleanly to the existing `SKILL.md` artifact format. Per the November 2025 Cloud Blog announcement, ADK was downloaded over 7 million times since its earlier-2025 launch, indicating durable platform investment.

**Mitigation for pre-1.0 SDK churn**: pin `google-adk` to a known-good version in `requirements.txt`; re-run eval suite on minor version bumps.

---

## R-3: Skill format

### Question
How should the existing Claude-style `SKILL.md` content be ported to the Gemini-native agent?

### Considered

| Approach | Notes |
|---|---|
| Flatten everything into the system prompt | Simple but loses lazy-loading benefits; sends ~10k tokens per invocation |
| ADK SkillToolset | Three-tier loading: L1 metadata always; L2 instruction body when relevant; L3 resources on-demand |
| External RAG retrieval | Treats the skill as data; loses the prescriptive framing |

### Decision

**ADK SkillToolset** with two skills (`slo-approval-review` always-load, `sre-principles-citation` on-demand). Roughly 80% token reduction on routine reviews vs. flattened-into-prompt.

---

## R-4: Grounding (RAG) source

### Question
What corpus should the agent ground on when it needs to cite source authority?

### Considered

- Google SRE Book (chapters 3, 4, 5 on SLOs and error budgets) — public, CC BY-NC-ND 4.0, foundational
- Google SRE Workbook (chapters on SLO setting and error budget policy) — same license
- Customer-private reliability standards — varies by customer
- Industry blogs and Medium posts — varying quality, not auditable

### Decision

Two-source corpus per customer datastore:
1. **Reseller-curated public corpus** (SRE Book + Workbook chapters), replicated to each customer's datastore
2. **Customer-private internal standards**, added on customer onboarding

Per Constitution Article III, Principle 3.3, no cross-tenant retrieval — replicate the public corpus rather than share a single index.

---

## R-5: Output format

### Question
Should the agent emit Markdown, JSON, both?

### Considered

- Markdown only — natural for the review paper; harder for downstream automation
- JSON only — machine-readable; loses the readability of a paper
- Both via structured output — Markdown is the paper, JSON is the verdict for automation

### Decision

**Both, via ADK's `output_schema`**. The agent emits a `ReviewVerdict` pydantic object whose `full_paper_markdown` field carries the human-readable paper and whose other fields carry the structured metadata. Downstream systems (Slack, ServiceNow, dashboards) consume the JSON; humans read the Markdown.

---

## R-6: Verdict stability under adversarial pressure

### Question
How do we prevent the agent from softening its verdict when users push back?

### Considered

- Instruct in system prompt only — model occasionally caves under repeated pressure
- Post-process the response and reject any verdict change without justification — works but brittle
- Section 7 of system prompt explicitly addressing pressure vs. new information + automated stability eval suite — belt and suspenders

### Decision

**Both.** Section 7 of the system prompt addresses pressure handling explicitly with concrete instructions ("Stand by the engineering judgment. New information moves the agent. Pressure does not."). Eval suite includes a stability suite that asserts verdict invariance across three pressure follow-ups per case.

This is the highest-leverage design decision in the product. Per Constitution Article II, Principle 2.2, the independence of the review IS the product. Any change here is a regression.

---

## R-7: Spec Kit fit

### Question
Does Spec-Driven Development map to maintaining an AI agent (as opposed to maintaining a traditional code project)?

### Considered

- Use Spec Kit for the agent's engineering process (this project)
- Treat the agent as Spec Kit's "subject under construction" — write spec, plan, tasks for new features (vertical prepends, new tools, new evals)
- Ship a Spec Kit extension so the agent's reviews are accessible from inside customer developers' Spec Kit-enabled coding agents

### Decision

**All three.** Spec Kit's primitives map naturally:

- The constitution corresponds to the agent's behavioral constraints and the engineering team's release discipline
- Specs correspond to new features (new vertical, new tool, new eval category)
- Plans correspond to architectural impact of new features
- Tasks correspond to ordered implementation
- The Spec Kit extension at `speckit-extension/speckit-slo-review/` adds `/speckit.slo-review` as a slash command for customer developers

See `07-speckit-integration.md` for the full integration story.

The one stretch: Spec Kit's primary design target is coding agents working on code projects. Treating an AI agent as the subject of SDD is a meta-use of the toolkit. Documented in the integration doc; raised proactively in customer architecture conversations.

---

## R-8: Cost model

### Question
What is the marginal cost per review at typical doc sizes?

### Measured

Inputs at typical sizes:
- Discovery doc: ~15,000 tokens
- Implementation guide: ~10,000 tokens
- System prompt: ~5,000 tokens
- Skill metadata (L1): ~200 tokens
- Total input: ~33,000 tokens

Outputs:
- Review paper Markdown + structured verdict: ~8,000 tokens

Cost (Gemini 3.1 Pro, May 2026 pricing):
- Input: 33k × $1.25/M = $0.041
- Output: 8k × $10.00/M = $0.080
- Vertex AI Search grounding (~5 queries × $0.004): $0.020
- Agent Engine runtime (~30 s): $0.001
- **Total: ~$0.14 per review**

### Decision

Marginal cost target of $0.20/review in the spec is met with comfortable headroom. Compute is not the constraint; reviewer time on the first N papers is.

---

## R-9: Region and residency

### Question
Where should Agent Engine and the supporting datastores be deployed?

### Decision

Customer-pinned region. Default `us-central1` for US customers; `europe-west4` for EU customers; equivalent for APAC. Agent Engine, GCS buckets, and Vertex AI Search datastores all co-located in the customer's pinned region. CMEK on every storage component.

Reasoning: data residency objections from regulated customers (pharma, gov, financial services) are the single most common deal-blocker for AI products serving F500. Solve it architecturally, not contractually.

---

## R-10: When to refresh this document

This research document is amended when:

1. A risk in `plan.md`'s risk register actually fires and changes our position (e.g., Gemini 3.1 Pro deprecated, ADK API breaks).
2. A foundation model or framework alternative becomes meaningfully better and warrants reconsideration.
3. A customer-specific deployment surfaces a new architectural decision worth capturing for the next customer.

Otherwise, this document is stable. Updates require a corresponding plan amendment and constitution compliance check.
