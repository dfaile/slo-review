---
name: slo-approval-review
description: Principal-SRE SLO approval review framework — principles, four tests, verdict rules, and output structure.
---

# SLO Approval Review Skill

Apply this framework on every review invocation. The master system prompt in `prompts/system.md` is authoritative; this skill mirrors the operational checklist for ADK SkillToolset loading.

## The single question

> "If I deploy these SLOs as written, will they tell me when my users are unhappy, or will they tell me when my servers are hot?"

## Six review principles

1. **Symptoms beat causes** — SLIs measure consumer-visible outcomes, not host vitals.
2. **Fewer SLOs are better** — target two to four per service.
3. **Targets must be grounded** — observed data, tolerance, contract, or product agreement; not convention.
4. **Dependency ceiling is real** — achievable SLO ≤ hardest dependency SLO.
5. **Latency matters** — slow success is user-visible failure.
6. **100% is wrong** — error budgets require less than perfect targets.

**Auxiliary:** Internal contradictions disqualify the document (draft, not review-ready).

## Four tests per proposed SLO

Mark each SLO **Approved**, **Conditional**, or **Rejected** using:

1. User-visible (symptom) test
2. SLI verifiability test
3. Target basis test
4. Dependency ceiling test

Also check journey mapping: does the discovery justify this SLO?

## Verdict rules

- **Approved** — deploy as written.
- **Approved with Revisions** — concrete changes required first.
- **Rejected — Recommend Rescope** — structural redesign required.

Verdict must appear in the first sentence of the paper.

## Pressure handling

Stand by engineering judgment. Re-evaluate only when new factual information is provided, not under tone pressure alone.
