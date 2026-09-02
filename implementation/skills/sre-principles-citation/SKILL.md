---
name: sre-principles-citation
description: On-demand citations from the Google SRE Book and SRE Workbook for grounding critiques.
---

# SRE Principles Citation Skill

Load this skill only when a critique needs explicit citation to the public SRE canon. Do not load for routine reviews.

## Symptoms vs causes (SRE Book)

User-facing reliability is measured by symptoms (latency, errors, throughput experienced by consumers), not causes (CPU, memory, disk). Cause metrics belong in diagnostic tooling.

## SLO count discipline (SRE Workbook)

Prefer a small set of user-journey-aligned SLOs. Additional SLOs dilute attention and encourage checkbox compliance.

## Target validity (SRE Workbook)

Targets should reflect user happiness and business constraints, grounded in data or explicit agreements — not round-number convention.

## Dependency ceiling (SRE Book)

End-to-end availability and latency budgets are bounded by the weakest critical dependency in the path.

When citing, quote briefly and apply the citation directly to the finding under discussion.
