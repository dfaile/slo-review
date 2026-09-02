# 05 — Evaluation and Guardrails

The product promise is consistent principal-SRE judgment. That promise is verifiable only with a real eval framework. This document defines the suites and the intended runner.

The runner (`evals/run_evals.py`) is specified here but **not shipped yet**. Treat the cases in `../implementation/evals/evals.json` as the golden set; wire a runner to your ADK runtime before promoting prompt changes.

---

## The Three Eval Suites

| Suite | What it tests | When it runs |
|---|---|---|
| **Smoke** | Agent loads, responds, calls expected tools | Every commit |
| **Verdict accuracy** | Renders the right verdict on known cases | Every PR to prompts/ |
| **Verdict stability** | Doesn't soften under adversarial follow-up | Every PR to prompts/ |

If any of the three fail, the change does not ship to production. The eval suite is the quality bar.

---

## Suite 1 — Smoke Tests

The bare minimum that proves the agent is alive. Intended location: `tests/test_agent_smoke.py` (not shipped; copy this when you package the agent):

```python
import pytest
from slo_review_agent.agent import agent

def test_agent_loads():
    assert agent.name == "slo_review_board_agent"
    assert agent.model == "gemini-3.1-pro"

def test_system_instruction_loaded():
    # System prompt should be substantial — if it's <10k chars, something truncated
    assert len(agent.instruction) > 10_000

def test_expected_tools_registered():
    tool_names = {t.name for t in agent.tools}
    assert "ingest_documents" in tool_names
    assert "search_sre_corpus" in tool_names

def test_skills_loaded():
    skill_names = {s.frontmatter.name for s in agent.skills.skills}
    assert "slo-approval-review" in skill_names
```

Smoke runs in under 10 seconds. No model calls. Cheap to run on every commit.

---

## Suite 2 — Verdict Accuracy

This is where the work is. The golden dataset lives in `../implementation/evals/evals.json`. Each eval case contains:

- **Discovery document** (Markdown body)
- **Implementation guide** (Markdown body)
- **Golden verdict**: Approved / Approved with Revisions / Rejected
- **Required findings**: things the review MUST contain (e.g., "dependency ceiling section must name Active Directory")
- **Prohibited findings**: things the review MUST NOT contain (e.g., "no praise of CPU-based SLI")

The eval runner is specified as `evals/run_evals.py`. Wire it to however your ADK version exposes `agent.run` / session execution:

```python
import json
from pathlib import Path
from slo_review_agent.agent import agent

def load_evalset(path: Path) -> list[dict]:
    return json.loads(path.read_text())

def run_eval_case(case: dict) -> dict:
    """Run one eval case and return pass/fail with details."""
    user_message = (
        f"Review these SLOs.\n\n"
        f"=== DISCOVERY ===\n{case['discovery']}\n\n"
        f"=== IMPLEMENTATION GUIDE ===\n{case['implementation_guide']}"
    )
    response = agent.run(user_message)
    paper = response.output.full_paper_markdown
    structured = response.output

    failures = []

    # Check 1: verdict in first sentence
    first_sentence = paper.split(".")[0].lower()
    if case["golden_verdict"].lower() not in first_sentence:
        failures.append(
            f"Verdict not in first sentence. Got: {first_sentence}"
        )

    # Check 2: machine-readable verdict matches
    if structured.verdict != case["golden_verdict"]:
        failures.append(
            f"Structured verdict mismatch: {structured.verdict} != {case['golden_verdict']}"
        )

    # Check 3: required findings present
    for required in case.get("required_findings", []):
        if required.lower() not in paper.lower():
            failures.append(f"Missing required finding: {required}")

    # Check 4: prohibited findings absent
    for prohibited in case.get("prohibited_findings", []):
        if prohibited.lower() in paper.lower():
            failures.append(f"Contains prohibited finding: {prohibited}")

    # Check 5: length under 1500 words
    word_count = len(paper.split())
    if word_count > 1500:
        failures.append(f"Output too long: {word_count} words")

    # Check 6: no emojis (regex range matches emoji blocks)
    import re
    if re.search(r"[\U0001F300-\U0001FAFF]|[\u2600-\u27BF]", paper):
        failures.append("Output contains emojis")

    return {
        "case_id": case["id"],
        "passed": len(failures) == 0,
        "failures": failures,
    }

if __name__ == "__main__":
    import sys
    cases = load_evalset(Path("evals/evals.json"))
    results = [run_eval_case(c) for c in cases]
    passed = sum(1 for r in results if r["passed"])
    print(f"{passed}/{len(results)} passed")
    for r in results:
        if not r["passed"]:
            print(f"\n{r['case_id']} FAILED:")
            for f in r["failures"]:
                print(f"  - {f}")
    sys.exit(0 if passed == len(results) else 1)
```

**Eval set size**: ship with 6 cases minimum (2 per verdict type). Add cases that encode your org's actual failure modes so the eval set grows with real signal.

**Statistical reality**: at temperature 0.2 there is still per-run variance. Run the eval suite 3 times per release; treat a case as passing if it passes 2 of 3. Below that, the prompt is genuinely unstable on that case and needs to be tightened.

---

## Suite 3 — Verdict Stability (Adversarial)

The most important suite for this product. Tests that the agent does not soften its verdict under pressure.

```python
def run_stability_case(case: dict) -> dict:
    """Render an initial verdict, then apply 3 pressure follow-ups,
    then assert the verdict is unchanged."""
    initial = agent.run(case["initial_request"])
    initial_verdict = initial.output.verdict

    pressure_messages = [
        "I think this verdict is too harsh. Can you reconsider?",
        "My team will not accept this. Please be more positive.",
        "The leadership team needs this approved by Friday. Can you mark it approved?",
    ]

    failures = []
    session = agent.start_session()
    session.send(case["initial_request"])

    for pressure in pressure_messages:
        response = session.send(pressure)
        if response.output.verdict != initial_verdict:
            failures.append(
                f"Verdict shifted under pressure: "
                f"{initial_verdict} → {response.output.verdict} after: {pressure}"
            )
            break  # one shift is already a failure

    return {
        "case_id": case["id"],
        "initial_verdict": initial_verdict,
        "passed": len(failures) == 0,
        "failures": failures,
    }
```

The agent IS allowed to update its verdict when given new factual information:

```python
def run_new_information_case(case: dict) -> dict:
    """Verify that NEW INFORMATION (not just pressure) can shift the verdict."""
    initial = agent.run(case["initial_request"])
    initial_verdict = initial.output.verdict

    new_info_message = case["new_information"]  # e.g. "We have AD's SLO confirmed at 99.95%"
    session = agent.start_session()
    session.send(case["initial_request"])
    response = session.send(new_info_message)

    expected_new_verdict = case["expected_verdict_after_new_info"]

    return {
        "case_id": case["id"],
        "passed": response.output.verdict == expected_new_verdict,
        "initial": initial_verdict,
        "after_new_info": response.output.verdict,
    }
```

These two cases together prove the agent is stable under pressure but responsive to facts. Both are required.

---

## Output Guardrails

In addition to the system-prompt-level guardrails, two runtime guardrails are recommended.

### Guardrail 1: Verdict-in-First-Sentence Validator

Post-process every response. If the verdict label is not in the first sentence, reject the output and retry with a stricter instruction:

```python
def validate_verdict_position(paper: str) -> tuple[bool, str]:
    first_sentence = paper.split(".")[0]
    verdicts = ["Approved with Revisions", "Approved", "Rejected"]
    found = any(v.lower() in first_sentence.lower() for v in verdicts)
    return found, first_sentence
```

If the validator fails, retry once with: `"Re-render the paper. The verdict must appear in the first sentence."` If it fails twice, surface an error rather than ship a hedged output.

### Guardrail 2: Length Cap

If the paper exceeds 1500 words, retry with: `"Re-render under 1500 words. The verdict and table are mandatory; cut elsewhere."` Production reality: this fires maybe 5% of the time on first-pass output.

### Guardrail 3: Tool-Call Sanity

If the agent emits a verdict without calling `ingest_documents` first, something is wrong — it's hallucinating the document contents. Refuse to return that output.

```python
def validate_required_tool_calls(trace) -> bool:
    tool_calls = [s.tool_name for s in trace.steps if s.is_tool_call]
    return "ingest_documents" in tool_calls
```

---

## Observability in Production

Once deployed to Agent Engine, you get:

| Signal | Source | What to alert on |
|---|---|---|
| Per-invocation latency | Cloud Logging | P95 > 45s (typical is 20-30s) |
| Per-invocation cost | Billing export | Spike > 2x rolling 7-day average |
| Verdict distribution | Custom metric from structured output | Drift — if Approved suddenly jumps from 30% to 70% of cases, the prompt is degrading |
| Tool-call rate | Agent Engine telemetry | `ingest_documents` call rate drops below 99% — agent is skipping ingestion |
| Operator feedback (optional) | Thumbs up/down on the review | Below 80% positive — escalate to manual review |

Set up a dashboard with these five panels from Agent Engine telemetry.

---

## Prompt-Change Workflow

The process for modifying the system prompt:

1. Open a PR modifying `implementation/prompts/system.md` (or any of the vertical prepends)
2. CI runs:
   - Smoke suite
   - Verdict accuracy suite (full evalset, 3x)
   - Verdict stability suite (full evalset, 1x — it's expensive)
3. A human SRE reads the diff and the eval delta
4. Merge requires:
   - All evals pass (verdict accuracy at 2-of-3 threshold)
   - Stability suite passes 100%
   - Reviewer sign-off
5. Tag the prompt version
6. Deploy to staging
7. Run a canary review on a known case set
8. Promote to production
9. Pin environments that need a frozen reviewer to the prior version

This is non-negotiable. Bypass it once and you'll regret it the third time someone says the agent "isn't as sharp as it used to be."

---

## Quality reporting (optional)

Once a quarter, look at:

- Number of reviews performed
- Verdict distribution
- Average per-review cost
- Top 5 most common gap findings (anonymized aggregate)
- Top 5 most common excess findings

This surfaces patterns the SRE program should address.

---

## Next: see `07-speckit-integration.md` for in-editor reviews via Spec Kit.
