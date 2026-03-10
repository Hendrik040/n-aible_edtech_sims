---
allowed-tools: Bash(git *), Bash(gh *), Bash(sleep *)
description: Commit, push, open a PR → then run the full CodeRabbit review loop
argument-hint: "[target-branch]  — defaults to develop-v2"
---

## Arguments

$ARGUMENTS contains the optional target branch. If empty, use `develop-v2`.

## Context (auto-collected)

- Current branch: !`git branch --show-current`
- Git status: !`git status --short`
- Commits ahead of origin/develop-v2: !`git fetch origin develop-v2 --quiet 2>/dev/null; git log origin/develop-v2..HEAD --oneline`
- Diff stat vs develop-v2: !`git diff origin/develop-v2...HEAD --stat`

---

## Your task — follow every step in order

### STEP 0 — Parse target branch

Set TARGET_BRANCH = the first word of `$ARGUMENTS`, or `develop-v2` if empty.

**HARD STOP**: If TARGET_BRANCH is `production` or `main`, refuse immediately and tell the user those branches are protected. Do not continue.

---

### STEP 1 — Verify there is something to PR

Look at the diff stat from the context above.

- If the diff vs `origin/develop-v2` is **empty**, tell the user there is nothing new to PR and stop.
- Otherwise summarise the changes in one sentence so the user can confirm they're opening the right PR.

---

### STEP 2 — Commit & push (if needed)

1. If there are **uncommitted changes** (`git status --short` is non-empty):
   - Stage everything relevant: `git add -A`
   - Write a clear conventional-commit message that reflects the actual diff
   - Commit: `git commit -m "..."`

2. Push the current branch to origin:
   ```
   git push origin HEAD
   ```
   If the branch doesn't exist on remote yet, use `--set-upstream`.

---

### STEP 3 — Open the PR

Create the PR targeting `TARGET_BRANCH`:

```
gh pr create \
  --base TARGET_BRANCH \
  --title "..." \
  --body "..."
```

PR body must include:
- **Summary** — bullet list of what changed and why
- **Test plan** — what was manually verified or how to test
- Footer: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`

Print the PR URL when done.

---

### STEP 4 — Wait for CodeRabbit (first review)

Tell the user:

> **Waiting 5 minutes for CodeRabbit's first review…**
> Do not merge yet. CodeRabbit will post inline comments and a summary.

Then sleep 300 seconds: `sleep 300`

---

### STEP 5 — Fetch & display CodeRabbit comments

Run these two commands and present all findings clearly:

```bash
# Summary comment
gh pr view <PR_NUMBER> --json comments \
  --jq '.comments[] | select(.author.login == "coderabbitai") | .body'

# Inline review comments
gh api repos/Hendrik040/n-aible_edtech_sims/pulls/<PR_NUMBER>/comments \
  --jq '.[] | {file: .path, line: .line, body: .body}'
```

Group comments by severity if possible (errors / warnings / nitpicks).

---

### STEP 6 — Triage each comment with the user

For **every** CodeRabbit comment, present it and ask the user one question:

> **Implement** this comment, or **skip** it with a reason?

**If implement** → make the code change, commit, push, then continue to the next comment.

**If skip** → you MUST post a reply on that specific comment thread explaining why. Use:

```bash
gh api repos/Hendrik040/n-aible_edtech_sims/pulls/<PR_NUMBER>/comments/<COMMENT_ID>/replies \
  -X POST \
  -f body="@coderabbitai <reason the user gave for not implementing this>"
```

**No comment may be left in silence.** Every CodeRabbit comment gets either a fix or a written reply. This is non-negotiable.

---

### STEP 7 — Wait for incremental re-review (if any fixes were pushed)

If any changes were committed in Step 6:

> **Waiting 3 minutes for CodeRabbit's incremental re-review…**

`sleep 180`

Then repeat Step 5 → Step 6 for any new comments.

Repeat until there are no new comments, or all remaining comments have been replied to.

---

### STEP 8 — Done

Print a summary:

- PR URL
- Comments implemented: N
- Comments skipped with reply: N
- Status: **Ready for human review / Merge when approved**

Remind the user: **do not merge until they give explicit approval.**
