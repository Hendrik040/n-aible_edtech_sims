---
name: pr-review-workflow
description: "Pull-request lifecycle discipline for the n-aible repo. Covers opening a PR (pre-flight CLI checks, body shape, test plan), setting up a 15-min cron follow-up so CR comments don't rot, closing CR review threads (addressed OR reply-with-reason — never silent), verifying Railway deploy before claiming done, and the narrow conditions when admin-merge is legitimate. Auto-invoke when opening a PR, addressing CR feedback, merging, or following up on a stuck review."
version: 0.2.0
triggers:
  - open (a )?pr
  - create (a )?pr
  - merge (a )?pr
  - coderabbit review
  - cr (feedback|comments?)
  - address pr
  - pr review (loop|cycle|follow[- ]?up)
  - review (approved|changes requested)
  - pr workflow
  - merge discipline
  - admin[- ]?merge
---

# PR Review Workflow — n-aible

This skill encodes the PR lifecycle that evolved during the
rewrite-agent-sdk track. The rules here are not theoretical — each
one exists because its absence cost real time (see the post-mortems
in each section).

**Target branch for every feature PR: `ralph-looped`**. Never target
`production-v3` or `staging-v2` directly from feature work. Staging
and prod are promotion targets reached via separate trunk → trunk
PRs, not from individual features.

---

## 0. Step 0 — CLI health probes (before anything else)

Every PR that touches infra OR merges via this workflow starts with:

```bash
gh auth status  >/dev/null 2>&1   || echo "⚠ gh needs auth"
railway whoami  >/dev/null 2>&1   || echo "⚠ railway needs auth"
neonctl me      >/dev/null 2>&1   || echo "⚠ neonctl needs auth"
daytona sandbox list >/dev/null 2>&1 \
  || echo "⚠ daytona not authed (use sandbox list, NOT organization list)"
```

If any probe fails: **stop and tell the user**. Don't try to re-auth
from automation — the OAuth flows need a browser. This step-0 gate is
the single discipline that would have prevented the 2026-04-13 deploy
crash.

---

## 1. Opening the PR

### Branch from the right base

- Feature branches: `ralph-looped-feature/<short-slug>` (matches
  existing convention on remote; hyphen separator, not slash, to
  avoid git ref-namespace conflicts)
- Per-rewrite-ticket branches: `ralph-looped-rewrite/phase-X.Y-<slug>`

```bash
git fetch origin ralph-looped
git checkout -b ralph-looped-feature/<slug> origin/ralph-looped
```

### PR title + body

- **Title** under ~70 chars, conventional-commit style
  (`feat(admin): ...`, `fix(ci): ...`, `docs(skills): ...`)
- **Body** must include a Test Plan with checkboxes. Checkboxes are
  NOT cosmetic — they're the merge gate (see Section 4).

Template:

```markdown
## Summary
<1–3 bullets — what this changes, why>

## Test plan
- [ ] <relevant local check 1 — e.g. `pnpm build` exits 0>
- [ ] <relevant local check 2>
- [ ] CodeRabbit passes (or all comments addressed / replied)
- [ ] Railway experimental deploy green (verify with
      `railway logs --environment experimental -s Backend --lines 30`
      AFTER merge, before claiming done)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

### Open

```bash
gh pr create --repo Hendrik040/n-aible_edtech_sims \
  --base ralph-looped \
  --title "<title>" \
  --body "$(cat <<'EOF'
<body above>
EOF
)"
```

**No admin-merge at this point.** Proceed to Section 2.

---

## 2. Cron follow-up — schedule at PR-open time

CodeRabbit reviews take 5–15 minutes. If you move on and forget, the
PR rots. Every time you open a PR, immediately schedule a cron to
come back.

### The cron to create

Use the `CronCreate` tool with a `*/15` schedule offset off `:00`/`:30`
so the API isn't slammed (common alignment hazard). Minute `7, 22, 37,
52` is every 15 min, avoids peak alignment:

```
cron:      "7,22,37,52 * * * *"
recurring: true
durable:   false   (session-only is fine for PR-lifetime monitoring)
prompt:    (see template below)
```

### Cron prompt template — copy-paste-fill

The prompt is self-contained — cron fires start with empty context, so
everything the job needs must be in the prompt text:

```
PR follow-up check for <PR_NUMBER>: <PR_TITLE>.

Every ~15 min until this PR is merged/closed:

1. gh pr view <PR_NUMBER> --repo Hendrik040/n-aible_edtech_sims \
     --json state,mergedAt,reviewDecision,mergeable,statusCheckRollup

2. Classify:
   - state=MERGED → celebrate, ask the user if the cron can be deleted
   - state=CLOSED (not merged) → report, ask for direction
   - reviewDecision=APPROVED AND mergeable=MERGEABLE → proceed to
     Section 3 "Merge gates" of the pr-review-workflow skill. Do NOT
     auto-merge without running the gates.
   - reviewDecision=CHANGES_REQUESTED → pull CR inline comments
     (gh api repos/.../pulls/<PR_NUMBER>/comments), address each
     per Section 3 comment-closure rules, push fixes to the same
     branch. Never open a new PR for fixes.
   - reviewDecision is empty AND age < 20 min → CR still cooking;
     just log and wait for the next fire.
   - reviewDecision is empty AND age > 30 min → nudge the PR
     (gh pr comment <PR_NUMBER> --body "@coderabbitai review")
     and log.

3. Keep responses ≤120 words unless actively addressing comments.
```

### Create it

```bash
# via CronCreate tool — pseudo-code
CronCreate(
  cron="7,22,37,52 * * * *",
  prompt=<the template above with <PR_NUMBER> + <PR_TITLE> substituted>,
  recurring=true,
  durable=false,
)
```

**Auto-expires after 7 days** — recurring sessions don't survive
past that. If a PR is still open after a week, re-create the cron.

### Clean up after merge

When the PR merges, `CronDelete` the job ID. Tell the user the id
when you create it so they can also manually cancel if they want.

---

## 3. Addressing CodeRabbit feedback

### Comment-closure rules (the non-negotiable part)

A PR does **NOT** merge until every CR comment has one of:

1. **Code fix** committed to the same branch
2. **Reply with a reason** on the exact thread explaining why we're
   skipping it. "False positive because X", "Project uses Postgres
   only so SQLite branch doesn't apply", "Deferred to follow-up
   because Y" — all valid. What's not valid:
   - Silent skip (no reply)
   - Reply without substance ("thanks", "noted")
   - Mass-clear ("addressing all in a later PR") — too hand-wavy

If CR posts 5 comments and you fix 3 + reply-with-reason on 2, that's
merge-ready per this rule. If you fix 5 and silently ignore 0, that's
also merge-ready. If you fix 4 and ignore 1 without reply — **not
merge-ready**. Post a reply first.

### Pulling comments

```bash
# summary review (the walkthrough + top-level decision)
gh pr view <PR> --repo Hendrik040/n-aible_edtech_sims --json reviews \
  --jq '.reviews[] | select(.author.login == "coderabbitai") | .body'

# inline line-specific comments
gh api repos/Hendrik040/n-aible_edtech_sims/pulls/<PR>/comments \
  --jq '.[] | select(.user.login | startswith("coderabbitai")) | {path, line, body}'

# replying to a specific inline comment (use the comment id from above)
gh api repos/Hendrik040/n-aible_edtech_sims/pulls/<PR>/comments/<COMMENT_ID>/replies \
  -X POST -f body="<your reply>"
```

### Pushing fixes

Fixes go to the **same feature branch**. Commit message:

```
<ticket-id or scope>: address CR feedback (round N)

<what changed, one bullet per addressed finding>
```

Don't open a new PR for CR fixes.

---

## 4. Merge gates (all must pass before clicking merge)

Before ANY `gh pr merge`:

| Gate | Pass criteria |
| --- | --- |
| **CR closed** | reviewDecision is `APPROVED` OR every CR comment has either a fix or a reply (see Section 3). Mass unaddressed comments → not ready. |
| **Test plan** | Every checkbox in the PR body is ticked, with the evidence line actually truthy (not just ticked optimistically). |
| **CI** | `gh pr checks <PR>` shows no `fail`. Pending checks → wait; never merge with red. |
| **Railway preview (if applicable)** | If the PR has a Railway preview env, its deploy must be SUCCESS. The experimental env deploy runs after merge, which is Section 5. |
| **Branch base** | Target is `ralph-looped`. Not production-v3, not staging-v2. |

### Merge command

```bash
gh pr merge <PR> --repo Hendrik040/n-aible_edtech_sims \
  --squash --delete-branch
```

`--squash` is the repo convention (matches the CLAUDE.md rule on
`ralph-looped`). `--delete-branch` cleans the feature branch on
GitHub automatically.

---

## 5. Post-merge verification — this is where #465 burned us

Merging is not "done". Railway's auto-deploy kicks off on push to
`ralph-looped`, and **Railway keeps serving the previous successful
deploy when a new one fails**. `/health` will return 200 even when
your changes never made it live. Evidence required:

```bash
# 1. latest deploy is SUCCESS, not FAILED
TOKEN=$(python3 -c "import json; \
  print(json.load(open('$HOME/.railway/config.json'))['user']['accessToken'])")
curl -s -X POST 'https://backboard.railway.app/graphql/v2' \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"{ project(id:\"b5155e2f-af3c-49e9-9edc-664878402e01\") \
      { services { edges { node { name \
          deployments(first:3) { edges { node { status createdAt } } } } } } } }"}'

# 2. the routes you added are live on openapi.json
curl -sfL https://backend-experimental-246c.up.railway.app/openapi.json \
  | jq '.paths | keys[] | select(contains("<new-prefix>"))'

# 3. runtime logs are clean
railway logs --environment experimental -s Backend --lines 30
```

Only after all three: report the PR as done, delete the follow-up
cron, update any downstream tracking.

### The `/health` trap

`/health` passing is a necessary signal, not a sufficient one. A
failed deploy + rolled-back-to-previous-version backend passes
`/health` fine. Always pair with step 1 above (latest deploy =
SUCCESS in GraphQL).

---

## 6. Admin-merge — when it's legitimate (rare)

`gh pr merge --admin` bypasses branch-protection checks. Use ONLY
when:

1. The blocking check is **globally broken**, not specific to this
   PR (e.g. a pre-existing legacy test hangs infinitely on every PR)
2. The diff under review doesn't touch the broken surface (the
   legacy hung test is in `backend/tests/`, your diff is in
   `backend/modules/admin/` — unrelated)
3. You write a PR comment explaining **exactly why** the override is
   justified, before running the merge, so the trail is public

Never admin-merge to clear backlog or because "it'll be fine".
Never admin-merge without a written justification. Every admin-merge
is audit-visible via `mergeable: UNKNOWN` on the PR after, and
reviewers will ask what happened.

If you find yourself admin-merging more than one PR per day, the
blocking check is the real problem — go fix it (as we did in #466).

---

## 7. Common failure signatures (learned the hard way)

| Symptom | Real cause | Fix |
| --- | --- | --- |
| Dashboard metrics all 0 | `GITHUB_TOKEN` not set on Railway → 60 req/hr unauth rate limit → dashboard falls back to 0 | `railway variables --environment experimental --service Backend --set "GITHUB_TOKEN=$(gh auth token)"` |
| Deploy "FAILED" but `/health` green | Railway rolled back to last-successful; new code isn't live | Check GraphQL deploy status; fix root cause; redeploy |
| `alembic: overlaps with other requested revisions` | `alembic_version` table has stale truncated row from old VARCHAR(17) column | See `.claude/skills/neon-postgres/PROJECT_NOTES.md` for the exact DELETE fix |
| Loop spins skipping tickets | `pr_already_open_for()` loose-search matched an unrelated PR | Edit the unrelated PR's body to remove the hash reference OR wait for the fix merged on ralph-looped |
| CR review never arrives | CR app temporarily down OR PR body too large | Nudge with `gh pr comment <PR> --body "@coderabbitai review"` |

---

## 8. Related skills (cross-reference)

| Skill | When relevant |
| --- | --- |
| [code-review](../code-review/SKILL.md) | Local CR pass before push — reduces comment count on the actual PR |
| [autofix](../autofix/SKILL.md) | Apply CR PR-bot comments in batch |
| [railway-deploy-check](../railway-deploy-check/SKILL.md) | Step 5 post-merge verification (full recipe) |
| [neon-postgres](../neon-postgres/PROJECT_NOTES.md) | DB-state gotchas (alembic_version truncation) |
| [daytona-sandbox](../daytona-sandbox/SKILL.md) | Auth-probe discipline (sandbox list, not organization list) |

---

## 9. Checklist — the 30-second read

Before clicking merge:

- [ ] All CR comments addressed OR replied-with-reason
- [ ] Test-plan checkboxes ticked with evidence
- [ ] CI is green (not pending)
- [ ] Cron follow-up created at PR-open time (and about to be deleted)

After merging:

- [ ] Railway latest deploy = SUCCESS (via GraphQL, not just /health)
- [ ] New routes live on /openapi.json (if applicable)
- [ ] No errors in `railway logs --lines 30`
- [ ] CronDelete the follow-up job
- [ ] User notified of completion with links

If every box is ticked, the PR is actually done. If not, it isn't —
regardless of what the GitHub UI says.
