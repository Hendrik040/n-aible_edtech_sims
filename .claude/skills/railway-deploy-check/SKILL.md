---
name: railway-deploy-check
description: "Verify a PR's deploy on Railway's experimental environment after push. Auto-invoke after opening a PR, after pushing new commits to an open PR, or when a CI check on the PR fails — to surface Railway deploy/build/runtime failures and pinpoint where the deploy broke."
version: 0.1.0
triggers:
  - railway.?deploy
  - railway.?check
  - railway.?status
  - railway.?logs
  - check.?deploy
  - verify.?deploy
  - deploy.?fail
  - deployment.?fail
  - experimental.?env
  - experimental.?deploy
  - deployment.?check
  - pr.?deploy
---

# Railway Deploy Check (experimental environment)

Verify the deployment health of a PR in Railway's `experimental`
environment (the one that tracks the `ralph-looped` branch). When a
Railway build or runtime crash caused a CI check to fail, this skill
identifies the exact log line that broke so you know what to fix.

## When to use

Auto-invoke after:
- `gh pr create` on a PR that targets `ralph-looped`
- `git push` adding new commits to an open PR
- Any CI check on the PR fails and you suspect the failure traces back
  to the Railway build or runtime (not, e.g., a unit-test failure)

Do **not** use this skill to diagnose `production-v3` or `staging-v2`
deploys — it only reads from `experimental`.

## Prerequisites

Verify before invoking:

- `railway` CLI is installed: `command -v railway`
- Session is authed: `railway whoami` exits 0
  (auth state lives in `~/.railway/config.json` — outside the repo;
  never read or print its contents)
- The Railway project is linked: from the repo root, `railway status`
  should name the `n-aible_edtech_sims` project

If any prerequisite fails, stop and report it to the user — do not try
to re-authenticate or write to `~/.railway/`.

## Security

- **Never** commit or print API keys, tokens, or the contents of
  `~/.railway/config.json` / `RAILWAY_TOKEN` / `RAILWAY_API_TOKEN`.
  The helper script only invokes the CLI; it does not read the auth
  config directly.
- If you notice a token-like string (`Bearer ey...`, `rw_...`,
  `sk_...`) in log output, stop the skill, redact, and warn the user.
- Do not add any hardcoded keys to helper scripts or SKILL.md.

## How to invoke

```bash
!`bash ${CLAUDE_SKILL_DIR}/scripts/check-deploy.sh $ARGUMENTS`
```

Optional args (space-separated service names): `Backend`, `Frontend`.
Defaults to both when none are given.

Example:
```bash
!`bash ${CLAUDE_SKILL_DIR}/scripts/check-deploy.sh Backend`
```

## What to report back

After the helper runs, summarize for the user:

1. **Per-service deploy status**: green / failed / in-progress.
2. **If any service failed**: the block of log lines around the
   failure (the helper prints these automatically with 30 lines of
   context). Call out the *specific line* that caused the crash —
   usually a `Traceback`, `FATAL`, `Build failed`, `Deployment failed`,
   or `exited with code N` marker.
3. **Correlation to the PR**: if the failure signature looks like it
   comes from files in the PR's diff, say so explicitly so the user
   knows a follow-up commit is needed. If the failure looks unrelated
   (e.g., an ambient env or secret problem), flag that too.
4. **If all green**: one-line confirmation and stop.

Keep the summary tight — the raw log block is already in the
output; don't repeat it verbatim, just point at the salient line.
