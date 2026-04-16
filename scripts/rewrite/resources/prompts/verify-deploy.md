PR #{{PR_NUM}} for ticket **{{TICKET_ID}}** (issue #{{ISSUE_NUM}}) has
just been squash-merged into `{{BASE_BRANCH}}`. Railway auto-deploys
`{{BASE_BRANCH}}` to the **experimental** environment. Your job is to
confirm that deploy came up healthy and that the merge didn't break
the backend at runtime.

This runs **after** merge, so a failure here does not block the merge
— but it does mean a human should triage before the next iteration.

## The skill to run

Use the **railway-deploy-check** skill. Invoke it by asking to verify
the experimental Railway deploy after merging PR #{{PR_NUM}}.

The skill will:
- Confirm the Railway CLI is authed (`railway whoami`). If not, follow
  its auth-recovery reference — do **not** improvise.
- Link the project to `experimental` / `Backend` non-interactively.
- Pull recent logs and look for startup error patterns (`Traceback`,
  `ImportError`, `ModuleNotFoundError`, `sqlalchemy.exc`,
  `alembic.*ERROR`, `FATAL`, `ERROR.*startup`).
- Hit the backend health endpoint and check for HTTP 200.

## Workflow

1. Invoke the skill.
2. If the skill reports healthy deploy → print the verdict below.
3. If the skill surfaces errors:
   - Summarize the failure (log line or health-check status).
   - Post a comment on PR #{{PR_NUM}} with the failure summary so
     whoever triages has immediate context:
     ```bash
     gh pr comment {{PR_NUM}} --repo {{GH_REPO}} \
       --body "Post-merge deploy verification failed: <short reason>. See logs."
     ```
   - Print the failure verdict. Do **not** try to fix-forward here;
     the next iteration will pick up from merged `{{BASE_BRANCH}}`.

## Output the verdict (the loop reads this)

At the very end of your output, print exactly **one** of:

- `DEPLOY_VERIFIED` — health endpoint green and no error patterns in
  recent logs.
- `DEPLOY_FAILED: <short reason>` — deploy came up unhealthy or logs
  show a startup/runtime error.

## Hard rules

- Never touch `staging-v2` or `production-v3` — only read from
  `experimental`.
- The merge has already happened; do not attempt to revert, reset, or
  force-push anything. If the deploy is broken, surface it and stop.
- Railway auth tokens expire silently. If `railway whoami` fails, the
  skill's auth-recovery reference is the only sanctioned path — don't
  prompt the user inline from this phase.
