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

## Prerequisites (in order — each one's failure is a distinct fix)

1. **CLI present**: `command -v railway`
2. **Session authed**: `railway whoami` exits 0 and names a user.
   - Railway's OAuth tokens **expire silently** — a stale token looks
     "logged in" in the config file but fails on any API call. Always
     probe with `railway whoami`, never trust presence of the config.
   - **If expired or unauthenticated**, follow
     [references/auth-recovery.md](references/auth-recovery.md) — do NOT
     guess the command or ask the user "can you log in". The reference
     gives the exact browserless (`railway login -b`) recovery flow, the
     user-facing template for surfacing the auth code, and the edge cases
     (token expired mid-session, wrong account, multiple accounts).
3. **Project + service linked**: needed so `railway logs` / `redeploy`
   / `variables` know what to target. Two paths:
   - Interactive: `railway link` then pick project + env + service
     (prompts in terminal; not usable from automation)
   - **Non-interactive (preferred for skills)**: known ids:
     ```bash
     railway link -p b5155e2f-af3c-49e9-9edc-664878402e01 \
                  -e experimental -s Backend
     ```
     The project id is not a secret — it's a stable identifier safe
     to hardcode. Secrets live in variables (see below), never in
     links.

If any prerequisite fails, stop and tell the user — do not try to
re-authenticate, write to `~/.railway/`, or guess at project ids.

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

## Operations beyond the helper (learned the hard way)

The `check-deploy.sh` helper covers the common case. For things the
helper doesn't do, here's what works reliably — each fell off a cliff
at least once before being documented:

### Listing recent deployments (build + deploy status)

`railway logs` alone doesn't show deploy outcomes. Query the
GraphQL API directly:

Official Railway guidance is to authenticate GraphQL calls with the
`RAILWAY_API_TOKEN` environment variable (account-scoped token,
generated at <https://railway.com/account/tokens>). Do **not** parse
`~/.railway/config.json` — the CLI login token there is brittle across
CLI versions and auth modes, and Railway engineers explicitly
discourage using it for automation.

```bash
: "${RAILWAY_API_TOKEN:?Set RAILWAY_API_TOKEN before running this command}"
curl -s -X POST 'https://backboard.railway.app/graphql/v2' \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ project(id:\"b5155e2f-af3c-49e9-9edc-664878402e01\") { services { edges { node { name deployments(first:5) { edges { node { id status createdAt } } } } } } } }"}'
```

Do NOT print `$RAILWAY_API_TOKEN` into logs or commits. Treat the full
GraphQL response as potentially-sensitive; extract only what's needed.

### Per-deployment runtime logs

Once you have a deployment id from the GraphQL call:

```bash
railway logs --environment experimental -s Backend <deploy-id-full-uuid>
```

If you get "Deployment not found", you're probably using a truncated
id. The id in `deployments(first:N)` is a full UUID; use that.

### Triggering a fresh deploy

After fixing something (variable change, external state cleanup),
force a redeploy:

```bash
railway redeploy -y   # requires --service linked
```

Setting env vars auto-triggers a redeploy, so use this only when
you changed external state (DB, another service) and need to
restart the backend.

### Setting / updating variables

```bash
railway variables --environment experimental --service Backend \
  --set "KEY=VALUE"
```

Triggers an automatic redeploy — usually desired. Two patterns we
use:

- `RALPH_EVENT_TOKEN` — shared secret for loop telemetry; generate
  with `openssl rand -hex 32` and set on Railway + local `.env`
  simultaneously.
- `GITHUB_TOKEN` — from `gh auth token`; required for the admin
  dashboard's "PRs merged / open issues" queries to avoid the 60
  req/hr unauthenticated rate limit. Without it, the dashboard
  silently shows 0 for GitHub-derived metrics.

Verify a variable is set without echoing its value:

```bash
railway variables --environment experimental --service Backend --json \
  | python3 -c "import json,sys; v=json.load(sys.stdin); \
                [print(f'{k}: {\"SET\" if v.get(k) else \"MISSING\"}') \
                 for k in ['GITHUB_TOKEN','RALPH_EVENT_TOKEN']]"
```

### The "stale deploy keeps serving" gotcha

Railway keeps the previous successful deploy running when a new one
fails. So `/health` can return 200 while the actual code you pushed
never made it live. Verification MUST include:

1. `/openapi.json` has the routes you just added (curl + jq)
2. Latest GraphQL deployment is `SUCCESS` not `FAILED`

One of these passing is not enough — we lost multiple hours learning
that `/health` on its own doesn't prove a deploy worked.
