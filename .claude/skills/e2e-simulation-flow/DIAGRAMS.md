# E2E Simulation Flow — Diagrams

Visual companion to [SKILL.md](SKILL.md) and
[scripts/run-e2e.py](scripts/run-e2e.py). Two linked flows executed
against the **experimental** environment only: a professor authors &
publishes a simulation, then a fresh student joins via invite and plays
it with scripted Q&A.

For the overall Ralph-loop context that invokes this skill at step 6b,
see [../../../scripts/rewrite/WORKFLOW.md](../../../scripts/rewrite/WORKFLOW.md).

## Environment (always experimental)

| Surface | Value |
| --- | --- |
| Backend URL | `https://backend-experimental-246c.up.railway.app` |
| Neon branch | `experimental-v2` |
| Neon project | `super-cherry-83189326` |

Override via `E2E_BASE_URL`, `NEON_BRANCH`, `NEON_PROJECT_ID` only if
explicitly asked.

---

## Flow 1 — Professor authoring

```
  new Session (cookies persist) ─ generated unique email per run
         │
         ▼
  1. POST /api/auth/users/register  {role=professor, email=e2e_prof_<ts>}
         │                              ┌──────────────────────────────────┐
         ├── 🛠 neon-postgres ─────────▶│ SELECT id FROM users             │
         │                              │ WHERE email=$1 AND role='professor'│
         │                              │ expect 1 row ✅                   │
         │                              └──────────────────────────────────┘
         ▼
  2. POST /api/auth/users/login  →  sets access_token cookie
         │       (cookie captured in session — reused for every call below)
         ▼
  3. POST /api/pdf-processing/parse-pdf  (multipart)
         │   file: scripts/test-fixtures/HBR_CaseStudy.pdf
         │   → simulation_id (draft)
         ├── 🛠 neon-postgres ─▶ SELECT id FROM simulations WHERE id=$1 ✅
         ▼
  4. POST /api/publishing/simulations/publish/{simulation_id}
         ├── 🛠 neon-postgres ─▶ SELECT id FROM simulations
         │                       WHERE id=$1 AND status='active' ✅
         ▼
  5. POST /professor/cohorts/  {name="E2E Cohort <ts>"}
         │   → cohort_id
         ├── 🛠 neon-postgres ─▶ SELECT id FROM cohorts WHERE name=$1 ✅
         ▼
  6. POST /professor/cohorts/{cohort_id}/simulations  {simulation_id}
         ▼
  7. POST /professor/cohorts/{cohort_id}/invites
         │   → invite_token
         ▼
  ✅  Flow 1 complete. Exports to Flow 2:
         { simulation_id, cohort_id, invite_token, run_id, professor_email }
```

---

## Flow 2 — Student playing the simulation

Flow 2 inherits `invite_token` + `simulation_id` from Flow 1 and shares
zero other state. Clean handoff, no hidden coupling.

```
  new Session (separate from professor's — student cookies only)
         │
         ▼
  1. POST /api/auth/users/register  {role=student, email=e2e_student_<ts>}
         ├── 🛠 neon-postgres ─▶ SELECT id FROM users
         │                       WHERE email=$1 AND role='student' ✅
         ▼
  2. POST /api/auth/users/login  →  student access_token cookie
         ▼
  3. POST /student/invitations/{invite_token}/respond  {"action":"accept"}
         │   → student joins cohort
         ▼
  4. POST /api/simulation/start  {simulation_id}
         │   → user_progress_id, current_scene
         ▼
  5. SCRIPTED Q&A LOOP  ──  fixtures/student-questions.json
     ┌──────────────────────────────────────────────────────────────┐
     │  for scene in scenes (scene_order 1..5):                     │
     │                                                              │
     │    for turn_text in scene.turns:     (2–3 turns per scene)   │
     │       POST /api/simulation/linear-chat                       │
     │          {user_progress_id, message: turn_text}              │
     │       ← assistant response                                    │
     │                                                              │
     │    POST /api/simulation/linear-chat                          │
     │       {user_progress_id, message: scene.advance_phrase}      │
     │    ← assistant response, scene advances                      │
     │                                                              │
     │  scene 5 complete ─▶ expect terminal state                   │
     └──────────────────────────────────────────────────────────────┘
         │
         ▼
  6. GET /api/simulation/progress/{user_progress_id}
         │   expect: completed_at populated   (fixture may need more scenes
         │                                     if simulation has > 5 scenes —
         │                                     warn but do not fail)
         ▼
  ✅  Flow 2 complete. End-to-end verdict:
         ┌────────────────────────────────────────────┐
         │  full round-trip PASSED                    │
         │  run_id: <ts>                              │
         │  rows NOT cleaned (experimental is scratch)│
         │  → inspect with neon-postgres skill if     │
         │    debugging a failed step                 │
         └────────────────────────────────────────────┘
```

## What each box is actually doing

- **new Session** — `requests.Session()` in `run-e2e.py`. Cookies persist across calls; each flow gets its own session.
- **🛠 neon-postgres** — DB-verify helper in `run-e2e.py:db_verify()` that either runs via `psycopg2` + the connection string from `neonctl cs`, or degrades to a warning if either is unavailable. The skill under `.claude/skills/neon-postgres/` is the authoritative reference doc.
- **Scripted Q&A loop** — iterates `fixtures/student-questions.json`. One POST per turn, one POST for the `advance_phrase`, next scene.
- **advance_phrase** — an explicit "I'm ready to move on" marker sent after each scene's regular turns. Simulations that use content-based scene transitions pick this up; ones that require an explicit API advance will need an adjustment (noted in SKILL.md's open-questions section).
