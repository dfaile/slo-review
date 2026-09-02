# Spec — SLO Review Board Agent

**Feature ID**: 001-slo-review-board-agent
**Status**: Implemented (Reference v1.0)
**Constitution version**: 1.0.0

> This spec describes WHAT the agent does and WHY. Technology and architecture choices live in `plan.md`. Implementation breakdown lives in `tasks.md`.

---

## Problem Statement

Enterprise SRE programs cannot scale principal-SRE-quality review of proposed SLO portfolios using human reviewers alone. The pattern is consistent across customers: service teams propose SLOs faster than the principal SREs can review them; the review backlog becomes a bottleneck; teams either ship un-reviewed portfolios (resulting in cause-based SLIs, ungrounded targets, and dependency-ceiling violations) or stall on adoption.

The reviewer's job is to answer one question for the service owner: *if I deploy these SLOs as written, will they tell me when my users are unhappy, or will they tell me when my servers are hot?* That judgment is well-codified (Google SRE Book and Workbook) but expensive to apply consistently at scale.

---

## What We Are Building

A deployed AI agent that ingests an SLO Discovery document and an SLO Implementation Guide together, applies the principal-SRE framework defined in the constitution, and produces a 1–3 page approval paper with a clear verdict, SLO-by-SLO evaluation, gaps, excess, and sign-off conditions.

The agent is the product. The framework is the IP. The deployment substrate (Gemini Enterprise Agent Platform) is the runtime.

---

## User Stories

### US-1 — Service team wants a review before submitting to the human review board

**As a** software engineer drafting an SLO implementation guide
**I want** an AI-rendered review of my proposal against my discovery document
**So that** I can fix obvious issues (cause-based SLIs, ungrounded targets, dependency-ceiling violations) before consuming a principal SRE's review-board time.

**Acceptance criteria:**
- The agent ingests my discovery document and implementation guide from a Cloud Storage prefix I specify.
- The agent returns a paper with a clear verdict in the first sentence.
- The agent identifies every cause-based SLI in my proposal.
- The agent identifies any target with no documented basis.
- The agent names every hard dependency in my discovery and states whether my targets are achievable given each dependency's known SLO.
- Round-trip latency from request to rendered paper is under 60 seconds at the 95th percentile.

### US-2 — Principal SRE wants to spot-check, not draft

**As a** principal SRE responsible for SLO sign-off across multiple service teams
**I want** AI-rendered reviews delivered before our review-board meetings
**So that** I spend my meeting time on the hard cases, not the cases that mechanical application of the framework would have caught.

**Acceptance criteria:**
- The agent's verdicts agree with my own judgment on 90%+ of routine cases.
- I can identify, in under 60 seconds, the cases that need my deeper attention by reading the verdict and SLO-by-SLO evaluation table.
- When I disagree with the agent's verdict, the agent's reasoning chain is concrete enough that I can pinpoint where we diverge.

### US-3 — SRE program owner wants consistency across the org

**As an** SRE program owner across many service teams
**I want** every team to get the same review applied to the same framework
**So that** the portfolio-level quality of our SLO program improves uniformly rather than depending on which reviewer a team gets.

**Acceptance criteria:**
- Two different teams submitting equivalent proposals receive equivalent verdicts.
- The agent's verdict distribution is observable to me: I can see Approved/Conditional/Rejected counts and the most common findings across all reviews in my org.
- The agent's framework matches the public SRE Book/Workbook so that teams can self-educate against the same standard the agent enforces.

### US-4 — Compliance/audit team wants an artifact

**As a** compliance owner in a regulated environment (GxP, FedRAMP, PCI)
**I want** every SLO portfolio change to ship with a documented review
**So that** auditors can verify our reliability practice has independent review built in.

**Acceptance criteria:**
- Every review produces a persistent, time-stamped, attributed paper.
- The paper is stored alongside the SLO config artifacts it reviews.
- The paper includes the vertical regulatory context applied (GxP / FedRAMP / PCI) when one applies.

### US-5 — Maintainers want to iterate the agent safely

**As an** engineer maintaining this agent
**I want** every change to the system prompt, vertical prepends, or eval set to pass an automated regression gate
**So that** trust in the agent's consistency does not degrade silently over time.

**Acceptance criteria:**
- Smoke, verdict-accuracy, and verdict-stability eval suites are runnable in CI.
- Eval failures block merge.
- Prompt changes are versioned semantically; deployments can pin versions.

---

## Success Criteria

| Metric | Target | How measured |
|---|---|---|
| Verdict agreement with principal-SRE spot-check | ≥90% on routine cases | QA during rollout |
| Verdict stability under adversarial follow-up | 100% | `verdict_stability` eval suite, every release |
| P95 round-trip latency | ≤60 s | Agent Engine telemetry |
| Per-review cost | ≤$0.20 at typical doc sizes | Billing export |
| Reviewer satisfaction (thumbs up rate) | ≥80% | Optional in-product feedback |

---

## Out of Scope

- **SLO generation.** A sibling skill (`slo-implementation-guide`) generates SLOs; this one reviews them. Two different products in the same suite.
- **SLO portfolio analytics.** Aggregating verdicts across an org over time is a separate workstream.
- **Auto-remediation.** The agent reviews; it does not modify the customer's SLO configuration. Modifications remain a human decision.
- **Non-SLO review.** The agent declines requests to evaluate document quality, code, project plans, or unrelated topics.

---

## Non-Functional Requirements

| Category | Requirement |
|---|---|
| Availability | Single-region Agent Engine deployment per customer; failover is the customer's choice. |
| Data residency | Customer-pinned region; CMEK on all storage. |
| Confidentiality | Per-customer Vertex AI Search datastores. No cross-tenant retrieval. |
| Auditability | Every invocation logged with timestamp, caller identity, input document URIs, and output verdict. Log exported to customer's Cloud Logging. |
| Cost | Marginal cost per review remains under $0.20 at the 95th percentile of input size. |
| Latency | P95 round-trip <60 s; P99 <120 s. |

---

## Open Questions (Resolve via `/speckit.clarify` Before Planning)

None remaining for v1.0. Pre-resolved questions from earlier drafts:

1. **Q**: Should the agent ground on the customer's own prior approved SLOs as additional context? **A**: Not in v1.0. Risk of self-reinforcing prior mistakes is higher than the benefit. Revisit in v1.2.
2. **Q**: Should the agent generate Nobl9/Grafana YAML when revisions are recommended? **A**: No. That's the sibling skill's job. Cleanly separate the review function from the authoring function.
3. **Q**: Should the agent support batch review of multiple services at once? **A**: Not in v1.0. Single-service invocations only. Batch may come in v1.3 if customer demand warrants.

---

## Constitution Compliance Check

This spec has been verified against `.specify/memory/constitution.md` v1.0.0:

- [x] Article I (Review Principles) — all six are reflected in the success criteria and acceptance criteria
- [x] Article II (Verdict Behavior) — US-2 acceptance criteria and the stability eval enforce this
- [x] Article III (Engineering Principles) — US-5 enforces 3.1, 3.2, 3.5; non-functional requirements enforce 3.3
- [x] Article V (Precedence) — out-of-scope section honors the constitution's scope limits
