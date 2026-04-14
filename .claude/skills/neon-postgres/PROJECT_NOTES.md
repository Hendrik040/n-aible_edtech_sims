# Neon — n-aible project notes (companion to SKILL.md)

The upstream `SKILL.md` covers Neon generally. This file captures
n-aible-specific learnings and the exact commands that worked (or
didn't) during the rewrite track.

## Project + branch identifiers (safe to hardcode)

These are stable, non-secret identifiers. Commands that pin them are
reliable across sessions:

| Thing | Value |
| --- | --- |
| Project id | `super-cherry-83189326` |
| Parent branch (stable) | `production` |
| **Target branch for rewrite work** | `experimental-v2` (note the `-v2` suffix) |
| Other branches | `develop-v2`, `staging-v2`, `pr-*` |

**Gotcha**: the Neon branch is `experimental-v2`, not `experimental`.
Railway's environment is called `experimental` (no `-v2`). Mixing
these up fails pre-flight checks with confusing errors.

## Auth probe that actually works

```bash
neonctl me
```

Returns a one-row table showing email + project limit when authed.
Anything else means the user needs to run `neonctl auth`. Token
lives at `~/.config/neonctl/` — never read or print its contents.

If `neonctl me` times out or returns an OAuth error, **stop and tell
the user**. Don't try to auth from automation — the OAuth flow
requires a browser.

## Connection strings — treat as secrets

```bash
DB_URL=$(neonctl connection-string \
  --project-id super-cherry-83189326 \
  --branch experimental-v2 2>/dev/null)
```

The returned URL contains a **password in cleartext** (`postgresql://user:password@host/db`).
Rules:

- Never print the full `DB_URL` to logs, PR comments, or files
- Never commit it to git
- When showing to the user, mask the password with a regex that
  replaces the `:password@` segment with `:****@` so the rest of the
  URL (scheme + user + host + path + query) stays visible for
  debugging:

  ```bash
  echo "$DB_URL" | sed -E 's#(postgres(ql)?://[^:]+):[^@]+@#\1:****@#'
  # → postgresql://app_user:****@db.example.com/mydb?sslmode=require
  ```

  Do **not** use `${DB_URL%\?*}` — that only strips query args and
  leaves the password in the output.
- When passing to `psycopg2.connect(...)`, pass the variable
  directly — don't log the connect call

## Direct SQL with psycopg2 (from the backend's venv)

The only Python env that has `psycopg2` readily available in this
repo is `backend/.venv`:

```bash
cd /Users/hendrikkrack/n-aible/re-write/n-aible_edtech_sims/backend
DB_URL=$(neonctl connection-string --project-id super-cherry-83189326 --branch experimental-v2 2>/dev/null)
uv run python <<EOF
import psycopg2
conn = psycopg2.connect("$DB_URL", connect_timeout=10)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM users")
print(f"users: {cur.fetchone()[0]}")
conn.close()
EOF
```

`psql` is NOT installed on this machine — trying `psql "$DB_URL"`
fails with `command not found`. Use the `uv run python` approach instead.

## alembic_version — watch out for column truncation

There's a latent bug in the experimental-v2 DB: the
`alembic_version.version_num` column was widened from `VARCHAR(17)` to
`VARCHAR(32)` at some point, but pre-existing rows weren't backfilled.
Symptoms:

```
ERROR [alembic.util.messaging] Requested revision X overlaps with
  other requested revisions Y
FAILED: Requested revision X overlaps with ...
```

This appears at backend startup during `alembic upgrade heads` when
the alembic_version table contains a TRUNCATED version string (e.g.
`add_code_language` instead of `add_code_language_to_scenes`).

**Fix** (already applied on 2026-04-13; document so the next
occurrence is instantly recognizable):

```python
import psycopg2
conn = psycopg2.connect(DB_URL, connect_timeout=10)
cur = conn.cursor()
cur.execute("SELECT version_num FROM alembic_version ORDER BY version_num")
rows = [r[0] for r in cur.fetchall()]
# Identify any truncated rows — they'll be shorter than the
# corresponding file's revision id. Delete them. Keep only the
# full, valid head.
cur.execute("DELETE FROM alembic_version WHERE version_num = 'add_code_language'")
conn.commit()
```

After cleanup, redeploy via Railway. The backend should start cleanly
on the next try. See `.claude/skills/railway-deploy-check/SKILL.md`
for the redeploy recipe.

## Branch management commands we actually use

```bash
# list branches (project_id is stable)
neonctl branches list --project-id super-cherry-83189326

# create a temp branch for migration testing
neonctl branches create \
  --project-id super-cherry-83189326 \
  --parent experimental-v2 \
  --name migration-test-$(date +%s)

# delete a temp branch
neonctl branches delete <temp-branch-name> \
  --project-id super-cherry-83189326
```

Always clean up temp branches — they count against the project's
branch limit.

## Ralph loop usage

The Ralph rewrite loop's `emit_event` helper writes to
`ralph_pipeline_events` on `experimental-v2`. For dashboard
validation queries (count events, verify schema, spot-check phase
distributions), use the psycopg2 recipe above.

Related tables on `experimental-v2`:
- `users` — test professors + students from E2E runs
- `simulations` — drafts from parse-pdf flow
- `prompt_traces` — LLM call traces (empty until simulations
  actually run on experimental)
- `ralph_pipeline_events` — phase-transition events (populated by
  the loop + backfill script)
- `alembic_version` — migration head (see truncation gotcha above)
