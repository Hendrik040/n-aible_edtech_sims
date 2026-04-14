# Railway CLI Auth Recovery

Procedure for recovering from an unauthenticated Railway CLI session, driven
from an agent context (no browser, no stdin).

## When this applies

Triggered by any of these signals:

- `check-deploy.sh` exits 2 with stderr:
  `ERROR: railway CLI not authed. See references/auth-recovery.md for recovery steps.`
- `railway whoami` exits non-zero (often with `Unauthorized` or
  `Not logged in. Please run \`railway login\``).
- Any `railway <cmd>` — `logs`, `variables`, `link`, `redeploy`, `status` —
  fails with `Unauthorized`, `401`, `Not logged in`, or a prompt to run
  `railway login`. Tokens expire silently, so a previously-working session
  can fail mid-task; the recovery is identical.

## Recovery procedure

1. Run **`railway login -b`** (browserless). Do NOT run plain `railway login` —
   it opens a browser and blocks on stdin, which an agent cannot drive.
2. Parse stdout for:
   - **Auth code**: 8 chars, format `XXXX-XXXX` (uppercase alphanumeric), on
     the line beginning `Your authentication code is:`.
   - **Activation URL**: `https://railway.com/activate` (on the `Please visit:`
     line).
3. Surface both to the user verbatim, using this template so formatting stays
   consistent across invocations:
   ```
   Railway CLI is not authenticated. To recover:
     1. Visit: https://railway.com/activate
     2. Enter code: HZXN-TCMF
     3. Approve in your browser (requires existing Railway login)
   Reply "done" once you've approved and I'll retry.
   ```
   (Replace `HZXN-TCMF` with the actual code from step 2.)
4. Wait for the user's "done". Do NOT poll `railway whoami` in a tight loop —
   trust the confirmation. Once received, run `railway whoami` once; if it
   still reports unauthenticated, report that to the user and ask them to
   redo step 3 (the approval click on `railway.com/activate`).
5. Retry the command that originally failed (the `check-deploy.sh` invocation,
   the `railway logs ...` call, whatever it was).

## What NOT to do

- Do NOT scrape Railway credentials from env vars, the macOS keychain,
  `~/.railway/config.json`, or anywhere else on disk. The recovery is the
  `login -b` flow above, period.
- Do NOT run a headless browser, Selenium, or similar to automate
  `railway.com/activate`. A Claude browser extension driving the user's
  existing session is a separate path — not this reference.
- Do NOT call plain `railway login` (without `-b`). It blocks on stdin and
  opens a browser on the user's machine; an agent cannot complete it.
- Do NOT attempt to "refresh" a token by writing to `~/.railway/config.json`.

## Edge cases

- **Token expired mid-session**: identical recovery — run `railway login -b`,
  surface code + URL, wait for "done", retry.
- **Wrong account** (user is logged into account A, needs to switch to B):
  `railway login -b` does NOT switch accounts inline. Run
  `railway logout && railway login -b` instead, then proceed from step 2.
- **Multiple accounts**: same as above — logout first, then browserless login.

## Future automation (out of scope)

A Claude browser extension with access to the user's logged-in Railway session
could click "Authorize" on `railway.com/activate` and collapse this into a
single step. Out of scope for this CLI-only reference, but worth noting for a
future author.
