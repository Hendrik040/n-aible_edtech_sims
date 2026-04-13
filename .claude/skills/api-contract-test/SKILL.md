---
name: api-contract-test
description: "After backend changes, verify that every API endpoint the Next.js frontend calls still returns the shape the frontend expects. Mocks frontend-side requests (auth cookies, JSON bodies, query params), hits the endpoint, compares the response against the OpenAPI contract, and diffs the live OpenAPI spec against the experimental-environment spec to surface any breaking change before the PR merges. Auto-invoke when a diff touches backend routers, schemas (dto.py / schemas/), services, or common/db models."
version: 0.1.0
triggers:
  - api.?contract
  - contract.?test
  - openapi.?(diff|change|break|regress)
  - frontend.?contract
  - backend.?api.?(change|break|regress)
  - endpoint.?(test|regress)
  - router.?test
  - schema.?change
  - dto.?change
---

# API Contract Test Skill

The Next.js frontend consumes roughly **100 backend endpoints** (see
`/openapi.json`) by path, method, body shape, response shape, and
status code. When the backend changes, this skill makes sure none of
those contracts silently broke.

The live contract lives at:

- Local (dev): `http://localhost:8000/openapi.json`
- Experimental (what `ralph-looped` deploys to): `https://backend-experimental-246c.up.railway.app/openapi.json`

`experimental` is the baseline — it's what the frontend currently
talks to when a user clicks around.

## When to use

Auto-invoke when a diff touches **any** of:

- `backend/api/**` (top-level routers)
- `backend/modules/*/router.py`
- `backend/modules/*/schemas/**` or any `dto.py`
- `backend/common/db/models/**` (models often appear in responses)
- `backend/common/db/base.py` / database-migration files
- Anything that changes a Pydantic model that appears in a response

Do **not** auto-invoke on pure internal-service refactors that don't
touch the router or schemas — run the probe and it'll report zero
affected endpoints.

## Architecture

```
backend/tests/
├── conftest.py                  ← in-memory SQLite, TestClient/AsyncClient fixtures (REUSE)
├── modules/<mod>/test_router.py ← existing router tests (behavior + basic contract) (REUSE)
└── contract/                    ← NEW home for contract-specific tests + fixtures
    ├── conftest.py               (auth helpers — seeded student / professor logins)
    ├── fixtures/
    │   ├── auth/login.json        (a realistic frontend login payload)
    │   ├── simulation/start.json  (what /start receives when a student clicks "Begin")
    │   └── …                      (one file per endpoint that takes a body)
    └── test_contract_<module>.py  (one test per endpoint, asserts status + response shape)
```

Convention: a fixture is JSON shaped like
```json
{
  "endpoint":   "POST /api/simulation/start",
  "auth":       "student",
  "request":    { "body": { "simulation_id": 1 }, "query": {}, "headers": {} },
  "expected":   { "status": 200, "required_fields": ["user_progress_id", "simulation", "current_scene"] }
}
```

The fixture is the "UI mock" — it must match what the frontend
actually sends. When the frontend's request shape changes, update the
fixture first, then the backend can change to match it.

## Prerequisites

- `jq`, `curl`, `python3` available.
- Backend reachable at **at least one** of:
  - `http://localhost:8000` (if the dev runs `uvicorn app.main:app --port 8000`)
  - `https://backend-experimental-246c.up.railway.app` (always, if network reachable)
- For running contract pytest: `cd backend && pytest tests/contract -q` (assumes
  `backend/tests/conftest.py` is intact).

## How to run

### 1. Probe affected endpoints (always run first)

```bash
!`bash ${CLAUDE_SKILL_DIR}/scripts/probe-api-contract.sh`
```

What it does:

1. Fetches `experimental`'s `/openapi.json` (baseline) → `/tmp/api-contract/remote.json`.
2. Tries `localhost:8000/openapi.json` (dev). If reachable, diffs
   against remote. Otherwise reports "no local backend — running
   against experimental only."
3. Scans the current git diff vs. `origin/ralph-looped`, maps touched
   files to router prefixes via a built-in module→prefix map, and
   lists the affected endpoints.
4. Prints a punch list of "this endpoint changed shape" /
   "this endpoint is new" / "this endpoint was removed" — each of
   those is a contract break the frontend will notice.

### 2. Run contract pytest for the affected modules

```bash
cd backend && python -m pytest tests/contract/ -q \
    -k "<prefix from probe output>"
```

If `tests/contract/` doesn't exist yet, it's a clean opportunity to
scaffold it — start with the module(s) whose endpoints appear in the
probe's "changed" list, not everything at once.

### 3. When you need to add a contract test for a newly-touched endpoint

- Drop a fixture at `backend/tests/contract/fixtures/<module>/<endpoint-slug>.json`.
- Add / extend `backend/tests/contract/test_contract_<module>.py`:
  - Parametrize over fixtures in the matching subfolder.
  - For each fixture: authenticate as `fixture["auth"]`, send the
    request, assert `response.status_code == fixture["expected"]["status"]`,
    assert every `required_fields` entry is present in the response body.
- Don't hand-craft exhaustive schemas — the OpenAPI spec already has
  those. Just assert status + required-field presence; that's what
  the frontend actually cares about.

## Security

- The fixtures **must not** contain real user passwords, emails, or
  session tokens. Use seeded test users (created in `conftest.py`) or
  synthetic UUIDs.
- The probe script **must not** send Authorization headers to
  experimental. It only GETs `/openapi.json`, which is public.
- If you see a real session token leak into a fixture or a log,
  stop, redact, and tell the user.

## What to report back

After the probe + pytest run, summarize:

1. **Affected endpoints** — list them with the kind of change
   (new / removed / shape-changed).
2. **Test status per endpoint** — pass / fail / missing test.
3. **Recommended follow-up** — for each failure: is this a
   legitimate contract break (frontend will break, you need to fix
   the backend) or an outdated fixture (frontend already changed,
   fixture needs refresh)?

Keep it short. The probe's raw output has the detail; your summary
should be decision-ready.
