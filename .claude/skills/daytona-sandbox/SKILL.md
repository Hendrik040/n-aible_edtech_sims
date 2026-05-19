---
name: daytona-sandbox
description: "Drive the Daytona CLI when a workflow needs to create, inspect, run code in, or tear down a sandbox — the ephemeral environment that powers the student code-challenge flow (execute-code endpoint, sandbox_service, grading for code_challenge scenes). Auto-invoke when implementing or testing anything that touches student code submission, business-analytics simulations, or the sandbox-related backend code."
version: 0.1.0
triggers:
  - daytona
  - sandbox(es)?
  - code.?challenge
  - execute.?code
  - sandbox.?service
  - business.?analytics.?sim
  - student.?code.?submission
  - sandbox.?scaling
  - sandbox.?state
---

# Daytona Sandbox Skill

The app uses **Daytona** ephemeral sandboxes to run student-submitted
code during `code_challenge` scenes (business-analytics simulations).
The Daytona CLI on this machine is authenticated and ready; use it
whenever the work you're doing could break — or needs to verify —
anything about that code path.

## Where Daytona is wired in the codebase

| Concern | File |
| --- | --- |
| Sandbox lifecycle (create/exec/upload/delete) | `backend/common/services/sandbox_service.py` (singleton, wraps `AsyncDaytona` SDK) |
| HTTP endpoint students hit | `POST /execute-code` in `backend/api/simulation.py` / `modules/simulation/router.py` |
| Sandbox provisioned on simulation start | `lifecycle_service.start_simulation()` — only when the scenario has `scene_type="code_challenge"` scenes |
| Code-challenge grading | `grading_agent._grade_code_challenge_scene()` (combines sandbox output with rubric) |
| DB field | `UserProgress.sandbox_id` (nullable) |
| E2E coverage | `frontend/e2e/code-editor-sandbox-recovery.spec.ts` |
| Scaling / capacity tests | `backend/tests/sandbox_scaling/test_parallel_sandbox_capacity.py` |
| Architecture notes | `daytona-architecture.md` (repo root) |

If your diff touches any of the above, or you're adding tests that
exercise the code-challenge path, invoke the CLI to probe real sandbox
state instead of guessing.

## When to use

Auto-invoke when the task involves:

- Implementing or changing anything in `sandbox_service.py`,
  `execute-code`, `grade_code_challenge`, or the `UserProgress.sandbox_id`
  field.
- Writing / extending tests for business-analytics scenes, code
  submission, or sandbox scaling.
- Diagnosing a grading regression on a `code_challenge` scene where
  the automated checks (`code_ran`, `columns_found`, `rows_sufficient`,
  `output_keywords`) behave unexpectedly.
- PR validation on a diff that touches the sandbox surface — confirm
  a fresh sandbox still provisions, `exec` still returns, and teardown
  still works end-to-end.

Do **not** use it for unrelated work — sandbox ops cost time and
occupy a quota.

## Prerequisites — two auth modes, two different probes

The Daytona CLI supports two auth modes and the right health-probe
differs by mode:

| Mode | How it authed | Auth probe that works | Commands that fail |
| --- | --- | --- | --- |
| **Browser (`daytona login`)** | OAuth, session in `~/.daytona/` | `daytona organization list` | — (full CLI works) |
| **API key** (env var or keyring) | pre-provisioned token | **`daytona sandbox list`** | `daytona organization list` fails with "not available when using API key authentication" |

On this machine, auth is **API-key mode** (the user chose this because
browser OAuth sessions drop frequently and only they can re-auth via
browser). Use `daytona sandbox list` as the probe:

```bash
command -v daytona || { echo "daytona CLI missing"; exit 2; }
# Works for BOTH auth modes, so it's the safe default probe.
daytona sandbox list >/dev/null 2>&1 || {
  echo "daytona CLI not authed — user must run 'daytona login' or set DAYTONA_API_KEY"
  exit 2
}
```

Do **not** fall back to `daytona organization list` — it will fail
under API-key auth and you'll incorrectly report "not authed" when
it's actually fine for every command this skill actually uses.

If the probe fails, stop and tell the user — only they can complete
the browser OAuth flow. Don't try `daytona login` from automation.

## Security

- `DAYTONA_API_KEY`, `DAYTONA_API_URL`, and `DAYTONA_TARGET` are
  project secrets. **Never** commit them, echo them, or write them
  into any file the loop produces.
- The CLI reads auth from `~/.daytona/` (outside the repo). Don't
  read that directory and don't copy from it.
- If you must create a sandbox during testing, **clean it up** when
  done (`daytona sandbox delete <id>`). Orphan sandboxes burn quota
  and money.

## Command recipes

### 1. Discover current state (read-only, safe)

Use the bundled helper for a one-shot human-readable probe:

```bash
!`bash ${CLAUDE_SKILL_DIR}/scripts/probe-sandboxes.sh`
```

Or directly:

```bash
daytona sandbox list -f json | jq -r '.[] | "\(.id[0:12])  \(.state)  snapshot=\(.snapshot // "-")  auto-stop=\(.autoStopInterval)m"'
daytona sandbox info <sandbox-id>
```

### 2. Create a throwaway sandbox for a test

```bash
# Create, capture the id — DELETE IT at the end of the test.
SANDBOX_ID=$(daytona sandbox create --format json | jq -r .id)
# ... run your exec commands ...
daytona sandbox delete "$SANDBOX_ID" --yes
```

Always wrap this in a `trap`/`finally` so a failing test still
triggers the delete.

### 3. Run code in an existing sandbox

```bash
daytona sandbox exec <sandbox-id> -- python -c "import pandas; print(pandas.__version__)"
```

For tests that need a file present, upload first via the Python SDK
(`sandbox_service.upload_file`) or via `daytona sandbox ssh`. The
CLI's `exec` runs commands but does not upload files.

### 4. Inspect sandbox snapshots (what the code-challenge flow boots from)

```bash
daytona snapshot list -f json | jq -r '.[] | "\(.name)  size=\(.size // "?")  created=\(.createdAt)"'
```

If a PR changes which snapshot the sandbox starts from, confirm the
new snapshot exists here before you trust the test.

### 5. MCP mode (optional — for richer integration)

`daytona mcp` exposes an MCP server. Only consider this if the task
explicitly calls for long-lived sandbox tooling; for most one-off
checks the plain CLI is simpler.

## What to report back

After running a probe, summarize for the user:

1. **State of relevant sandboxes** — active / archived / failed count.
2. **Any failures or unexpected states** — e.g., sandboxes stuck in
   `pulling-image`, grown past the expected per-student count, or
   snapshot mismatches.
3. **If you created a sandbox**: confirm you also deleted it.
4. **If you're mid-debug**: the exact `exec` command that reproduced
   (or failed to reproduce) the behavior, so the user can rerun it.

Keep it short — this skill's job is to surface ground truth about the
sandbox layer, not to narrate.
