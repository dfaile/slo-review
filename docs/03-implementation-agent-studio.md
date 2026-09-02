# 03 — Implementation: Gemini Enterprise Agent Studio

This is the **low-code path** for Gemini Enterprise Agent Studio (Google Cloud console). Target time: **60–90 minutes from zero to first review**, plus datastore setup if you use GCS-backed document tools.

Official references:

- [Design agents in Agent Studio](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agent-studio/design-agents)
- [Deploy an agent to Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/deploy-an-agent)
- [Manage deployed agents](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/manage-deployed-agents)

---

## Agent Studio vs Agent Designer (do not mix them up)

| Surface | Where | Use for this product |
|---------|--------|----------------------|
| **Agent Studio** | Google Cloud console → **Agents** (Gemini Enterprise Agent Platform) | ✅ **This guide** — build, test in Preview, deploy to Agent Runtime |
| **Agent Designer** | Gemini Enterprise **web app** (tenant UI, “New agent” prompt) | Employee self-serve agents inside Gemini Enterprise chat — different UX, not these steps |
| **ADK / code-first** | Repo + CLI | See `04-implementation-adk-code-first.md` if Studio is not required |

Follow the steps below in the **Cloud console**, not the Gemini Enterprise web app designer.

---

## Prerequisites

| Item | Notes |
|------|--------|
| Google Cloud project | Billing enabled |
| IAM | Grant builders **Agent Platform User** (`roles/aiplatform.user`). Admins may also need roles to create data stores and deploy — see [Set up Agent Studio](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agent-studio/design-agents#set-up-your-environment) |
| APIs | `aiplatform.googleapis.com`, `discoveryengine.googleapis.com` (Agent Platform Search), `storage.googleapis.com` |
| GCS bucket | For discovery + implementation guides (CMEK recommended in production) |
| Prompt file | Full text from `02-master-system-prompt.md` (or use `implementation/prompts/system.md`, which is already extracted) |

Optional later: register the deployed agent in the **Gemini Enterprise** web app so employees can pick it from the agent list (see [Register ADK agents](https://docs.cloud.google.com/gemini/enterprise/docs/register-adk-agents) after deploy).

---

## Step 1 — Open Agent Studio and create an agent

1. In the [Google Cloud console](https://console.cloud.google.com/), open **Gemini Enterprise Agent Platform** → **Agents** (or search “Agents” in the console).
2. Click **Create agent**. The **Agent Studio canvas** opens.
3. On the **Flow** tab you should see a single **main agent** node. Click it to open the **Details** panel on the right.

Set in **Details**:

| Field | Value |
|-------|--------|
| **Name** | `SLO Review Board Agent` |
| **Description** | `Reviews SLO discovery and implementation guide pairs; returns a principal-SRE approval paper with verdict, per-SLO evaluation, gaps, and sign-off conditions.` |

Do **not** add subagents unless you later split ingestion into a separate step — one main agent with tools is enough for v1.

---

## Step 2 — Model and generation settings

In the same **Details** panel:

| Setting | Value |
|---------|--------|
| **Model** | `gemini-3.1-pro` (or latest Pro-tier model available in your project) |
| **Temperature** | `0.2` (if exposed in UI; otherwise set after export via ADK or in advanced settings) |
| **Max output tokens** | `8192` or highest allowed |

If the Studio UI does not expose temperature, keep the model on Pro and validate consistency in Preview; tune via **Get code** → ADK only if needed.

**Safety:** leave default harm filters — this agent is technical, not user-facing creative content.

---

## Step 3 — Instructions (system prompt)

In **Details → Instructions**, paste the **entire** horizontal prompt:

- Source: `02-master-system-prompt.md`, section **“The Prompt (copy verbatim…)”**, **or**
- File: `implementation/prompts/system.md`

**Regulated verticals (GxP / FedRAMP / PCI):** prepend the matching block from `02-master-system-prompt.md` (Customization for Verticals) **above** the main prompt, or use `implementation/prompts/vertical-gxp.md` (etc.) as the prepend.

Verify length (~22k characters). Truncated prompts are the #1 cause of weak verdicts and missing “pressure handling” behavior.

### Calibration examples (recommended)

Agent Studio does not use a separate “Playbook” object — examples belong in **Instructions** or in **Preview** test messages. Append a short block after the main prompt:

```markdown
## CALIBRATION EXAMPLES (for tone only — do not copy into production papers)

### Example A — Approved with Revisions
User provides discovery + impl guide for notification-service (see package eval case-02).
Expected verdict first sentence: Approved with Revisions. Must call out Redis queue health as cause-based.

### Example B — Rejected — Recommend Rescope
User provides order-fulfillment portfolio with five cause-based SLOs (see package eval case-03).
Expected verdict first sentence: Rejected — Recommend Rescope.
```

Full text for test runs lives in `implementation/evals/evals.json` and `samples/` (see Step 7).

---

## Step 4 — Default tools: turn off what you do not need

In **Details → Tools**, Agent Studio enables by default:

- **Google Search**
- **URL context**

For SLO review, **disable both** unless you explicitly want web/URL grounding. They add noise, cost, and data-governance risk.

---

## Step 5 — Agent Platform Search data stores (document + SRE corpus)

Create data stores **before** wiring tools. See [Get started with custom search](https://cloud.google.com/generative-ai-app-builder/docs/try-it-search) and [Set up tools in Agent Studio](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agent-studio/design-agents#set-up-and-add-tools-in-agent-studio).

### 5a — Review documents datastore

1. Index content from `gs://[your-bucket]/slo-review/` (one folder per service recommended).
2. Note **Project number**, **Location**, **Data store ID**, and **Collection ID** (`default_collection` if none).

### 5b — SRE corpus datastore

Index Google SRE Book / Workbook excerpts and organization-specific reliability standards in a **separate** datastore from review-document uploads.

### 5c — Grant Agent Platform Search access

On **IAM**, grant **Discovery Engine User** to:

`service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com`

(Replace `PROJECT_NUMBER` with your project number — required for Agent Platform Search tools.)

### 5d — Add tools on the agent

In **Details → Tools → Add (+)**, choose **Agent Platform Search Data Store** twice (or one combined store if your governance model allows):

| Tool purpose | Display name (suggested) | Data store |
|--------------|------------------------|------------|
| Review docs | `ingest_documents` | `slo-review-docs` store |
| SRE grounding | `search_sre_corpus` | `slo-review-sre-corpus` store |

In **Instructions**, add one short paragraph so the model knows when to call each store (the master prompt already describes ingestion; reinforce):

```markdown
When the user references a GCS path or uploaded documents, query the review-documents
data store. When you need to cite the SRE Book or Workbook, query the SRE corpus store.
```

### 5e — Nobl9 (optional, enterprise tier)

If needed, add an **MCP Server** or **OpenAPI** tool per Studio support in your project. Skip if you are not integrating Nobl9.

---

## Step 6 — Test in Preview

1. Open the **Preview** tab on the Agent Studio canvas (not a separate “Playground” product).
2. Run a test **without** relying on sample filenames that are not in the package.

**Option A — Paste eval case (fastest):**

Copy `discovery` and `implementation_guide` from `implementation/evals/evals.json` → `case-03-rejected-majority-cause-based` into one user message:

```
Please review these SLOs.

=== DISCOVERY ===
[paste discovery field]

=== IMPLEMENTATION GUIDE ===
[paste implementation_guide field]
```

**Option B — Package samples:**

Use the files in `samples/` (same content as eval cases, formatted as Markdown documents).

3. Confirm:

- Verdict in the **first sentence**
- Every proposed SLO appears in the evaluation table
- Cause-based SLIs called out on case-03
- Markdown section order matches the prompt
- Under ~1500 words, no emojis, no hedging

If Preview fails, re-paste Instructions from `implementation/prompts/system.md` and re-run case-03 before case-01.

---

## Step 7 — Deploy to Agent Runtime

1. From the **Agents** list, open your agent → **Deploy** (or **Deploy** on the agent detail page after Studio save).
2. In **Deploy to an Agent Runtime instance**:
   - Set **Display name** / **Description** for operators
   - Choose **Region** (data residency: `us-central1`, `europe-west4`, etc.)
3. Click **Deploy**. Expect **up to ~5 minutes**; completion shows on the **Flow** tab.

### Record the resource name (required for engine-mode Spec Kit reviews)

After deploy:

1. Go to **Agent Platform** in the console (deployed agents / runtime list for your region).
2. Open the deployment and copy **Resource name**, format:

   `projects/{project}/locations/{location}/reasoningEngines/{reasoning_engine_id}`

3. Set in the environment that will call engine-mode reviews:

   ```bash
   export SLO_REVIEW_AGENT_ENGINE_RESOURCE="projects/.../locations/.../reasoningEngines/..."
   ```

Also documented in [Manage deployed agents](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/manage-deployed-agents).

---

## Step 8 — Expose the agent to users

Pick one or more surfaces:

### A — Preview / console (builders)

Keep using Agent Studio **Preview** for internal SRE iteration.

### B — Gemini Enterprise web app (employees)

After Agent Runtime deploy, a **Gemini Enterprise admin** registers the agent so it appears in the tenant app. See [Register and manage ADK agents](https://docs.cloud.google.com/gemini/enterprise/docs/register-adk-agents) (runtime-hosted agents use the same registration flow).

Prerequisites on the tenant: **Agent Designer** / agent features enabled per [Agents overview](https://docs.cloud.google.com/gemini/enterprise/docs/agents-overview) if your org uses employee-made agents alongside registered ones.

### C — API / CI (`streamQuery`)

For PR gates and automation (Spec Kit **engine** mode, custom pipelines):

```bash
curl -X POST \
  "https://REGION-aiplatform.googleapis.com/v1/${SLO_REVIEW_AGENT_ENGINE_RESOURCE}:streamQuery" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "messages": [{
        "role": "user",
        "content": "Review these SLOs.\n\n=== DISCOVERY ===\n...\n\n=== IMPLEMENTATION GUIDE ===\n..."
      }]
    }
  }'
```

### D — Embedded widget / Slack

Only if your Gemini Enterprise / Agent Platform subscription exposes those integrations in console — configuration varies by tenant. Treat as optional services work, not blocking for Studio POC.

---

## Common pitfalls (Agent Studio)

| Symptom | Fix |
|---------|-----|
| Agent uses web search for every review | Disable **Google Search** and **URL context** (Step 4) |
| Verdict buried in paragraph 3 | Instructions truncated — re-paste full `implementation/prompts/system.md` |
| Agent softens verdict on follow-up | Section 7 (tone / pressure) missing from Instructions |
| “Cannot read GCS documents” | Data store not indexed, wrong Collection ID, or missing `gcp-sa-aiplatform-re` Discovery Engine role |
| Deploy succeeds but Spec Kit engine mode fails | `SLO_REVIEW_AGENT_ENGINE_RESOURCE` not set to full `reasoningEngines/...` name |
| Built in Agent Designer by mistake | Rebuild in **Cloud console → Agents → Create agent** (this guide) |

---

## Deploy checklist (Agent Studio)

- [ ] Agent created in **Cloud console Agent Studio** (Flow + Details), not only Agent Designer
- [ ] Instructions = full `implementation/prompts/system.md` (+ vertical prepend if applicable)
- [ ] Google Search + URL context **off**
- [ ] Review-docs + SRE corpus data stores wired with correct IAM
- [ ] Preview pass on `case-03` and one real doc pair
- [ ] Deployed to Agent Runtime; **resource name** recorded
- [ ] `SLO_REVIEW_AGENT_ENGINE_RESOURCE` set for engine-mode `/speckit.slo-review`
- [ ] (Optional) Agent registered in Gemini Enterprise web app
- [ ] Audit logs → Cloud Logging sink; cost alert configured

---

## Next steps

- **Programmatic CI/CD:** `04-implementation-adk-code-first.md`
- **Spec Kit in-editor reviews:** `07-speckit-integration.md`
- **Eval gate before prompt changes:** `05-evaluation-and-guardrails.md`
