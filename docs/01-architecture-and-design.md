# 01 — Architecture and Design

## Design Goals

The agent must do four things well:

1. **Render decisive verdicts.** A reviewer that hedges is worse than no reviewer. The agent must commit to Approved / Approved with Revisions / Rejected in the first sentence of every paper.
2. **Survive adversarial inputs.** Service owners will push back. The agent must not soften its verdict because the user is unhappy with it. The independence of the review *is* the product.
3. **Stay grounded in Google SRE principles.** Every judgment must trace back to symptoms-over-causes, dependency ceiling, target validity, or SLO count discipline. The agent is not generating opinions — it is applying a known framework.
4. **Run cheaply enough to scale.** Per-review compute cost must stay under a few dollars at typical document sizes so the agent can sit in a PR workflow, not a quarterly workshop.

These goals drive every architectural decision below.

---

## Why Gemini Enterprise Agent Platform

At Cloud Next '26 (April 2026) Google rebranded Vertex AI as the **Gemini Enterprise Agent Platform**, consolidating Agent Builder, Agent Studio, ADK, Agent Engine, Model Garden, and Vertex AI Search into a single agentic platform. For this use case, the platform is the right choice for four reasons:

1. **Long-context reasoning at production cost.** Gemini 3.1 Pro handles 1M-token context windows. An SLO Discovery doc + Implementation Guide together rarely exceed 30k tokens — comfortably inside the model's working set with room for the full system prompt, examples, and grounded SRE corpus.
2. **Native Skill support in ADK.** ADK's `SkillToolset` class loads skills via a three-tool pattern (`list_skills`, `load_skill`, `load_skill_resource`) that lets the existing `slo-approval-review` SKILL.md be ported with minimal restructuring. This is unusual — most agent platforms require flattening skills into a monolithic prompt.
3. **Agent Engine managed runtime.** Removes the operational burden of running agents 24/7. Call the agent via Cloud Run-style endpoints, Slack apps, or the SDK.
4. **Enterprise governance.** Native agent identities, IAM, VPC Service Controls, customer-managed encryption keys, and audit logging. Required for regulated production deployments.

The alternatives considered and rejected:

| Alternative | Why rejected |
|---|---|
| OpenAI GPT-5 + LangGraph | LangGraph is fine engineering but you carry the runtime, observability, and governance. Lengthens security review for regulated buyers. |
| AWS Bedrock Agents | Less mature skill/tool primitives. Forces a different cloud allegiance. |
| Claude on Anthropic API direct | Strongest model for this task, but no managed agent runtime. You'd need to build identity, governance, deployment yourself. |
| Self-hosted open-source (Llama, Mistral) | Reasoning quality is not yet at the level needed for principal-SRE judgment on technical correctness. Will be reconsidered in 12 months. |

The single largest risk in this stack is **Google's rapid renaming and reorganization** — "Vertex AI" became "Gemini Enterprise Agent Platform" mid-2026. The architecture itself is stable; the marketing names will shift again. Document the console names you actually used.

---

## Model Selection

**Primary reasoning model: `gemini-3.1-pro`**

Justification: principal-SRE judgment is the hardest part of the job. The model must:

- Hold both documents (discovery + implementation guide) in active reasoning simultaneously
- Apply abstract criteria (symptoms vs. causes) to concrete proposals
- Detect internal contradictions (e.g., exec summary claims 3 SLOs but body defines 8)
- Cite the Google SRE Book corpus accurately when challenged

Gemini 3.1 Pro is the only currently-available frontier model on the platform with reliable performance across all four. Gemini 3.1 Flash is acceptable for the document-summarization sub-agent (cheaper, 3x faster), but the verdict-rendering agent should always be Pro.

**Optional secondary model: `claude-opus-4-7` via Model Garden**

Some teams prefer Claude's reasoning style for this task and the Gemini Enterprise Agent Platform supports Claude Opus through Model Garden. Treat it as an optional reviewer model, not the default — the cost delta is meaningful and most routine reviews will not show a quality difference.

**Model parameters:**

| Parameter | Value | Reasoning |
|---|---|---|
| `temperature` | `0.2` | Low. The reviewer should be consistent across runs of the same input. Verdict stability is a feature. |
| `top_p` | `0.95` | Standard. |
| `max_output_tokens` | `8192` | Sufficient for the 800–1500 word target paper plus structured output overhead. |
| `system_instruction` | Master prompt | See `02-master-system-prompt.md`. |

Do not expose temperature to end users. The product promise is consistency.

---

## Deployment Paths

Two paths are documented. Both end at the same agent behavior; they differ in operational profile.

### Path A: Gemini Enterprise Agent Studio (low-code)

**When to choose:** First POCs. Teams standardized on **Gemini Enterprise Agent Platform** in the Google Cloud console. Pilots where a visual builder is required before ADK.

**How it works:** In the console **Agents** page, **Create agent** opens the Agent Studio canvas (**Flow** + **Details**). The system prompt goes in **Details → Instructions**. Tools are **Agent Platform Search** data stores (and optional MCP/OpenAPI). Test in the **Preview** tab; **Deploy** creates an **Agent Runtime** `reasoningEngines` resource. End users may use Preview, API `streamQuery`, or (after admin registration) the Gemini Enterprise web app.

**Trade-offs:**
- ✅ Setup in roughly an hour for a builder with console access
- ✅ Admin-friendly: Instructions can be tuned in the GUI
- ❌ Less testable: no programmatic eval harness
- ❌ Harder to embed in existing workflows (Slack/Jira/GitHub)
- ❌ Complex multi-agent Flow graphs get unwieldy; keep a single main agent for SLO review

See `03-implementation-agent-studio.md` for the step-by-step.

### Path B: ADK (code-first)

**When to choose:** Production deployments. Integration into existing workflows (Slack bots, ServiceNow, GitHub Action on PR-to-SLO-config repos). This repo's reference implementation.

**How it works:** Python module using the `google-adk` SDK. The system prompt is loaded as the agent's `instruction`. Tools are Python functions decorated for ADK. Skills are loaded via `SkillToolset`. Deploy to Agent Engine via `adk deploy`. Integrate via the Agent Engine SDK or REST endpoints.

**Trade-offs:**
- ✅ Fully testable: eval suite runs in CI/CD on every prompt change
- ✅ Embeddable: ship as a library, deploy as a Cloud Run service, or wrap in a Slack/Teams app
- ✅ Version-controllable: prompts, tools, skills all live in git
- ❌ Requires Python competence to set up and operate

See `04-implementation-adk-code-first.md` for the full code.

### Which path to start with

Use Path A to prove the prompt in console Preview. Move to Path B when you need CI, versioned prompts, or an embeddable endpoint. Both paths must emit the same verdict structure.

---

## Skill Architecture

ADK's `SkillToolset` implements a three-tier loading pattern that this product takes advantage of:

| Tier | Tool | Purpose |
|---|---|---|
| L1 | `list_skills` | Returns lightweight metadata (name + description) for all available skills. ~100 tokens per skill. |
| L2 | `load_skill` | Loads the full instruction body of a named skill. ~1500 tokens for slo-approval-review. |
| L3 | `load_skill_resource` | Loads supporting resources (templates, example outputs, SRE Book excerpts). |

For this product, two skills are recommended:

1. **`slo-approval-review`** — the primary skill. The full SKILL.md content lives in the L2 tier. Loaded on every invocation since the agent's job is approval review.
2. **`sre-principles-citation`** — a smaller skill containing exact quotes and chapter references from the Google SRE Book and Workbook. Loaded conditionally when the agent needs to ground a critique ("you said this was cause-based — what does the SRE Book say about that?").

Why two skills rather than one big prompt: the L2 instruction body for `slo-approval-review` is ~1500 tokens. Loading it every time is fine. The SRE Book citations are ~5000 tokens and only needed maybe 20% of invocations. Splitting them saves ~80% of grounding tokens on routine reviews. Per-review cost drops accordingly.

---

## Grounding (RAG) Configuration

The agent should be grounded on a private corpus that includes:

1. **Google SRE Book and Workbook** — public, licensed under CC BY-NC-ND 4.0. You can ground on these but cannot redistribute the text verbatim.
2. **Organization-specific reliability standards** — internal SRE handbooks, regulatory guidance (FedRAMP, GxP, PCI), or prior approved SLO portfolios belong in a private datastore.
3. **Prior reviews (optional)** — anonymized verdicts and reasoning from earlier reviews are useful calibration context. Keep them tenant-scoped.

Implementation: Vertex AI Search datastore, tenant-scoped. The agent's `tools` list includes a `search_sre_corpus` retrieval tool that queries the datastore when grounding is needed. See `05-evaluation-and-guardrails.md` for the grounding evaluation methodology.

---

## Security and Compliance

| Concern | Control |
|---|---|
| Document confidentiality | Per-tenant GCS bucket with CMEK; agent invocation scoped via IAM to that bucket only |
| Cross-tenant data leakage | Vertex AI Search datastores per tenant; no shared retrieval index |
| Prompt injection (malicious content in discovery docs) | Input sanitization + the master prompt's explicit "ignore embedded instructions" clause (see prompt section 7) |
| Audit trail | Agent Engine logs every invocation; export to an org-owned Cloud Logging sink |
| Data residency | Agent Engine respects region pinning; deploy to the preferred region |
| Regulatory (HIPAA, FedRAMP High) | Google Cloud's existing compliance posture covers most cases; verify with your security team before production |

For regulated verticals (pharma, finance, gov), expect a 4–6 week security review before production.

---

## Cost Model

Per-review cost at typical input sizes (15k token discovery + 10k token impl guide + 8k token output):

| Component | Tokens | Unit cost (May 2026) | Cost |
|---|---|---|---|
| Input (Gemini 3.1 Pro) | 33,000 | $1.25 / 1M | $0.041 |
| Output (Gemini 3.1 Pro) | 8,000 | $10.00 / 1M | $0.080 |
| Vertex AI Search grounding | ~5 queries | $4 / 1k queries | $0.020 |
| Agent Engine runtime | ~30 sec | $0.10 / hr | $0.001 |
| **Total per review** | | | **~$0.14** |

Compute cost is not the constraint. The constraint is whether you run the eval suite before promoting a prompt change. Plan reviewer time accordingly.

---

## Next: read `02-master-system-prompt.md` to see the core prompt that does the work.
