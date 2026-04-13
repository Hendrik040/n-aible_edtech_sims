You are writing a **changelog entry** that will be posted to our Canny
board (non-technical users + stakeholders read this) for PR
#{{PR_NUM}} which just merged into `ralph-looped`.

The PR implements ticket **{{TICKET_ID}}** (issue #{{ISSUE_NUM}}).

---

## PR context

**Title:** {{PR_TITLE}}

**Body:**
{{PR_BODY}}

**Files touched ({{DIFF_FILE_COUNT}}):**
{{DIFF_FILE_LIST}}

**Diff size:** +{{DIFF_ADDED}} / -{{DIFF_REMOVED}} lines

---

## What to produce

Emit **exactly one JSON object** at the end of your output — nothing
else after it. Schema:

```json
{
  "title": "<post title, 30–80 chars, non-technical>",
  "body":  "<post body, 2–5 sentences, plain English>"
}
```

### Writing rules for the title

- **Non-technical.** If the PR talks about `pgvector`, say "search
  index" / "AI memory". If it mentions `Alembic migration`, say
  "database update". `MCP tool` → "AI helper tool". `SSE` → "live chat
  streaming". Translate, don't transliterate.
- **Benefit-framed** when possible — what does this unlock for users
  or the business? ("Faster scene grading", "New PDF case-study
  upload flow", etc.)
- **Do not** include the ticket id, PR number, phase number, branch
  name, or CodeRabbit verbiage in the title.

### Writing rules for the body

- 2–5 sentences. Plain English. Active voice.
- Lead with the user / professor / student impact. Tech details go in
  one trailing sentence at most.
- Mention the ticket id once at the very end for traceability:
  `Tracked as {{TICKET_ID}}.`
- **Always** finish the body with a linkback line on its own:
  `→ Pull request: https://github.com/{{GH_REPO}}/pull/{{PR_NUM}}`
- Do **not** mention API keys, connection strings, Neon branch names,
  Railway env names, or other internal infra jargon. Those don't
  belong on a user-facing changelog.

## Output requirement

Print your JSON object as the **last thing** in your output. The
orchestrator will `json.loads` whatever trails the final ``` fence.
Any preamble (thinking out loud) before the JSON is fine, but once
the JSON block closes, print nothing else.

Example of acceptable trailing JSON:

```json
{"title": "Faster onboarding for new cohorts", "body": "Professors can now create a cohort, upload a case study, and send invites in a single guided flow instead of three separate steps. The change also tightens the backend validation so students no longer see intermittent errors when joining right after a cohort is published. Tracked as phase-2.4.\n→ Pull request: https://github.com/Hendrik040/n-aible_edtech_sims/pull/438"}
```
