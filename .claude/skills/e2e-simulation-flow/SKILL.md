---
name: e2e-simulation-flow
description: "Run the full end-to-end happy-path against the experimental environment: a fresh professor creates an account, uploads a sample case-study PDF, publishes the simulation, creates a cohort, assigns the simulation, and issues an invite. Then a fresh student registers, joins via the invite, and plays the simulation with a scripted Q&A sequence through every scene. Every mutating API call is cross-checked against the Neon `experimental-v2` branch via the neon-postgres skill. Auto-invoke before declaring a backend change complete, or whenever the diff could plausibly affect the professor-authoring or student-simulation flow."
version: 0.1.0
triggers:
  - e2e
  - end.?to.?end
  - full.?flow
  - happy.?path
  - simulation.?flow
  - professor.?flow
  - student.?flow
  - smoke.?test
  - integration.?test
---

# End-to-End Simulation Flow (experimental env)

Two linked flows executed against the **experimental** environment.
They prove the full user journey — professor authors a simulation,
student plays it — still works after a backend change. If the diff
broke any endpoint in either flow, this skill surfaces exactly which
step blew up and what the DB said at that moment.

## Environment (always experimental — never prod/staging)

| Surface | Value |
| --- | --- |
| Backend URL | `https://backend-experimental-246c.up.railway.app` |
| Railway env | `experimental` |
| Neon project | `super-cherry-83189326` |
| Neon branch | `experimental-v2` |

Override with env vars only if explicitly asked:
`E2E_BASE_URL`, `NEON_BRANCH`, `NEON_PROJECT_ID`.

## When to use

Auto-invoke when:

- A diff touches routing, auth, publishing, cohort, student-instance,
  or simulation-chat modules — i.e. anything in the two flows below.
- You're preparing a PR for merge into `ralph-looped` and haven't yet
  proven the full round-trip works.

Skip when:

- Only docs / CI / tooling files changed.
- The dev is iterating locally and hasn't opened a PR yet — local
  CodeRabbit + api-contract-test are cheaper first passes.

## Flow 1 — Professor authoring

Sequential API calls against the experimental backend. After each
mutating call, the orchestrator (see `scripts/run-e2e.py`) queries
Neon `experimental-v2` via the **neon-postgres** skill to confirm
the row landed.

| Step | Endpoint | DB check |
| --- | --- | --- |
| 1 | `POST /api/auth/users/register` (role=professor, unique email per run) | `SELECT id FROM users WHERE email = $email AND role='professor'` → exactly 1 |
| 2 | `POST /api/auth/users/login` — capture `access_token` cookie | auth cookie present in response |
| 3 | `POST /api/pdf-processing/parse-pdf` — multipart upload of `scripts/test-fixtures/HBR_CaseStudy.pdf` | row in `simulations` (draft) with matching `created_by`; session PDF data stored |
| 4 | `POST /api/publishing/simulations/publish/{id}` | `simulations.status = 'active'` AND `published_version_id` populated |
| 5 | `POST /professor/cohorts/` | new row in `cohorts` with `created_by = professor.id` |
| 6 | `POST /professor/cohorts/{cohort_id}/simulations` — assign | new row in `cohort_simulations` linking the two |
| 7 | `POST /professor/cohorts/{cohort_id}/invites` | new row in `cohort_invites` with non-expired `token` |

Output of Flow 1: `invite_token` (passed to Flow 2).

## Flow 2 — Student playing the simulation

| Step | Endpoint | DB check |
| --- | --- | --- |
| 1 | `POST /api/auth/users/register` (role=student, unique email) | row in `users` with role='student' |
| 2 | `POST /api/auth/users/login` — capture cookie | — |
| 3 | `POST /student/invitations/{token}/respond` with `{"action":"accept"}` | row in `cohort_memberships` linking student to cohort |
| 4 | `POST /api/simulation/start` | new `user_progress` row; first scene loaded |
| 5 | For each scene: read scripted turns from `fixtures/student-questions.json`, `POST /api/simulation/linear-chat-stream` or `/linear-chat` | 1 assistant row per turn in `conversation_logs`; `agent_sessions.session_id` stable across turns within a scene |
| 6 | Advance to next scene via the orchestrator-defined trigger (`I'm ready to proceed` phrase in the fixture, or `POST` endpoint if the backend exposes one) | `user_progress.current_scene_id` advances |
| 7 | After the last scene: confirm completion | `user_progress.completed_at` populated OR terminal scene's `scene_progress` marked complete |

Output of Flow 2: pass/fail summary + row counts per table.

## Prerequisites

```bash
# backend reachable
curl -sfL --max-time 5 https://backend-experimental-246c.up.railway.app/health

# neonctl authed + can see the experimental-v2 branch
neonctl branches list --project-id super-cherry-83189326 | grep experimental-v2

# the fixture PDF is in the worktree (it lives on ralph-looped)
test -f scripts/test-fixtures/HBR_CaseStudy.pdf

# python + requests
python3 -c 'import requests'
```

If any prerequisite fails, stop and tell the user. Don't run a
partial E2E — it's noisier than running none.

## How to invoke

### Pre-flight (fast, non-mutating)

```bash
!`bash ${CLAUDE_SKILL_DIR}/scripts/experimental-health.sh`
```

Confirms the backend + Neon + Daytona surfaces all respond.

### Run the full flow

```bash
!`python3 ${CLAUDE_SKILL_DIR}/scripts/run-e2e.py`
```

Exits 0 on full pass. Non-zero with a phase label + the failing
step's response body on the first break. Test users get a
timestamp-suffixed email so reruns don't collide; they're **not**
cleaned up automatically (the experimental DB is a scratch space).

### Scripted student Q&A

The student's turn content lives at
`${CLAUDE_SKILL_DIR}/fixtures/student-questions.json` — one object
per scene with:

```json
{
  "scene_order": 1,
  "turns": [
    "Hi, I'm ready to start. Can you tell me about the case?",
    "What are the key challenges the company faces?"
  ],
  "advance_phrase": "Thanks — I'm ready to move to the next scene."
}
```

If the simulation being tested has more or fewer scenes than the
fixture covers, the orchestrator emits a warning and runs as far as
the fixture goes — then tell the user to extend the fixture.

## Security

- `DATABASE_URL` / `NEON_API_KEY` / session cookies **never** get
  committed, printed in full, or written to skill files. The
  orchestrator masks cookie values when logging; `neonctl` reads
  auth from `~/.config/neonctl/` (outside the repo).
- Generated test-user passwords are random and held only in memory
  for the duration of the run.
- Do **not** point this skill at `production-v3` or `staging-v2`
  environments — it mutates the DB.

## What to report back

After a run, summarize:

1. **Per-step status** — ✅ / ❌ per step in each flow, with the
   failing step highlighted.
2. **DB evidence** — row counts / IDs that were written, proving
   the API call actually persisted.
3. **Trace pointer** — if any step failed, the generated test-user
   email (so the dev can find the half-written data in Neon) and
   the relevant Railway log excerpt via the `railway-deploy-check`
   skill.
4. **Overall verdict** — safe to merge / fix X first.
