You are on branch `{{FEATURE_BRANCH}}` with an open PR #{{PR_NUM}}
targeting `{{BASE_BRANCH}}` for ticket **{{TICKET_ID}}**
(issue #{{ISSUE_NUM}}).

There is new feedback on the PR you need to address. **Push fix
commits to this same branch — do NOT open a new PR.**

This is review round {{ROUND}} of {{MAX_ROUNDS}}.

---

## Overarching discipline — follow the pr-review-workflow skill

Follow the **pr-review-workflow** skill throughout this phase. It
encodes the comment-closure rule (every CR comment gets either a
code fix OR a reply-with-reason — never silent), the merge gates
(Section 4), and the post-merge Railway verify (Section 5). The
skill auto-invokes on "cr feedback" / "address pr" / "merge"
phrasing, so you don't need to slash-command it explicitly — just
let it shape your approach. If this phase ends with open CR comments
that have neither a fix nor a reply, you have NOT finished the round.

---

## Sources of feedback to check

### 1. CodeRabbit PR bot (always)

The bot posts inline comments on specific lines + a summary review on
the PR conversation. Use the **autofix** skill — it fetches the
comments via `gh api`, groups them by severity, and applies fixes
interactively or in batch. Invoke the skill by asking to address the
CodeRabbit review comments on PR #{{PR_NUM}}.

### 2. Railway deploy on the experimental env (always)

A failed deploy often shows up as a red CI check *after* the PR was
pushed. Use the **railway-deploy-check** skill — it pulls recent
experimental-env logs for Backend + Frontend and highlights the
failure marker (Traceback, Build failed, exited with code N, etc.).
Invoke it by asking to verify the PR deploy on experimental.

If the deploy failed because of code in this PR's diff, that stack
trace line is your bug indicator — fix the corresponding file.

---

## Workflow

1. Run the **autofix** skill. Address each actionable finding. If a
   finding is a false positive, say so briefly in the commit message.
2. Run the **railway-deploy-check** skill. If it reports failure
   markers, fix the underlying bug in the code.
3. Before pushing, re-run the **code-review** skill once on your
   local diff so the next PR-bot round stays quiet.
4. Commit:
   ```
   {{TICKET_ID}}: address PR review (round {{ROUND}})

   <what changed, one bullet per finding>
   ```
5. Push to the same branch: `git push`.

---

## Hard rules

- Stay on `{{FEATURE_BRANCH}}`. Never push to `{{BASE_BRANCH}}` or
  any other branch.
- Keep every change inside the ticket's `files` allowlist. If a CR
  finding asks you to change something outside the allowlist, push
  back in the commit message rather than expanding scope.
- Do not run the testing skills (api-contract-test,
  e2e-simulation-flow) in this round — those run after the review
  cycle is resolved, in a separate phase.
- If you cannot address the feedback (e.g., CR asks for something
  the ticket scope forbids): print
  `SKIP_ROUND: <reason>` and exit without pushing.
