You are implementing ticket **{{TICKET_ID}}** — issue #{{ISSUE_NUM}} —
in the n-aible EdTech platform rewrite.

Working directory: this worktree, forked off `{{ANCHOR_BRANCH}}`.
PR target: `{{BASE_BRANCH}}`.
Feature branch you must create: `{{FEATURE_BRANCH}}`.

---

## Ticket specification (this is the authoritative scope)

{{TICKET_SPEC}}

---

## CodeRabbit implementation plan (use as your guide, but the ticket spec above wins on conflicts)

{{CR_PLAN}}

---

## Skills available in this worktree

Project skills are installed under `.claude/skills/` and auto-invoke
based on description match. Relevant ones for this phase:

- **code-review** — invoke by asking for a CodeRabbit review of your
  local changes. Runs `coderabbit review --agent` against the diff
  and returns structured findings.
- **neon-postgres** — guidance for querying the experimental Neon
  branch if you need to verify DB state during implementation.

## Workflow (complete ALL steps — do not stop halfway)

### 1. Orient
Read `CLAUDE.md` and `scripts/rewrite/WORKFLOW.md`. Skim the skill
SKILL.md files that match your task.

### 2. Create the feature branch
```
git checkout -b {{FEATURE_BRANCH}}
```

### 3. Implement ONLY the scope above
- Stay inside the files listed in the ticket's `files` line.
- Match the `unit_tests_required` list exactly — each named test
  function must exist in the matching test file.
- Match `contract_tests_required` the same way.

### 4. Self-review locally with CodeRabbit
Ask for a review of your local changes. The `code-review` skill will
fire automatically and return findings. Iterate until it has no
actionable feedback (false positives can be noted and skipped).

### 5. Commit
First commit is the fix:
```
{{TICKET_ID}}: <one-line summary>

Fixes #{{ISSUE_NUM}}

<what changed and why — grounded in the ticket scope>
```
Second commit (separate) is the tests:
```
test({{TICKET_ID}}): cover <cases>
```

### 6. Push and open the PR
```
git push -u origin {{FEATURE_BRANCH}}
gh pr create --repo {{GH_REPO}} --base {{BASE_BRANCH}} \
  --label {{LABEL}} \
  --title '{{TICKET_ID}}: <summary>' \
  --body 'Fixes #{{ISSUE_NUM}}

Implements ticket {{TICKET_ID}}. See the issue for the full spec.

## Changes
<bullet list>

## Tests added
<bullet list>'
```

### 7. Output the PR number (the loop reads this)

Print this exact line at the very end of your output:
```
PR_NUMBER=<number>
```

---

## Hard rules

- **Stay in scope.** Files outside the ticket's `files` allowlist
  must not change. The PR reviewer rejects scope drift.
- **No infrastructure edits** (`.env`, `docker-compose.yml`, CI
  workflows) unless the ticket's scope explicitly says so.
- **No new dependencies** unless the ticket's scope calls for them.
- **No force pushes.** No `--no-verify`, no `--amend` on pushed
  commits — always create new commits.
- **Never touch `staging-v2` or `production-v3`.** Only branches
  forking off `{{ANCHOR_BRANCH}}` and PR-targeting `{{BASE_BRANCH}}`.
- If you cannot complete the ticket (blocker, missing tool, unclear
  spec): print `SKIP_ITERATION: <reason>` and exit without pushing.
