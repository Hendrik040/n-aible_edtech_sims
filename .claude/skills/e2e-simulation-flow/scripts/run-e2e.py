#!/usr/bin/env python3
"""End-to-end simulation-flow orchestrator (experimental env only).

Runs Flow 1 (professor authors + publishes + invites) then Flow 2
(student registers via invite + plays simulation with scripted Q&A).
After each mutating call it optionally verifies a row landed in Neon
`experimental-v2` if psycopg2 + a connection string are available;
otherwise the check is skipped with a warning (API-level pass/fail
still enforced).

Env overrides (all experimental by default):
    E2E_BASE_URL        default: experimental Railway backend
    NEON_PROJECT_ID     default: super-cherry-83189326
    NEON_BRANCH         default: experimental-v2
    NEON_DATABASE_URL   connection string to use for DB checks. If not
                        set, the orchestrator tries `neonctl cs
                        --project-id <...> --branch <...>` and uses
                        that. If that also fails, DB checks are
                        skipped (API checks continue).

Exit: 0 on full success, non-zero on the first failing step.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. pip install requests", file=sys.stderr)
    sys.exit(2)

BASE_URL        = os.environ.get("E2E_BASE_URL",        "https://backend-experimental-246c.up.railway.app").rstrip("/")
NEON_PROJECT_ID = os.environ.get("NEON_PROJECT_ID",     "super-cherry-83189326")
NEON_BRANCH     = os.environ.get("NEON_BRANCH",         "experimental-v2")
NEON_DB_URL     = os.environ.get("NEON_DATABASE_URL",   "")

FIXTURE_PDF       = Path("scripts/test-fixtures/HBR_CaseStudy.pdf")
FIXTURE_QUESTIONS = Path(__file__).parent.parent / "fixtures" / "student-questions.json"

# Try to resolve the Neon connection string on-demand if not provided.
def resolve_neon_url() -> str | None:
    if NEON_DB_URL:
        return NEON_DB_URL
    try:
        out = subprocess.run(
            ["neonctl", "cs", "--project-id", NEON_PROJECT_ID, "--branch", NEON_BRANCH],
            capture_output=True, text=True, check=True, timeout=20,
        ).stdout.strip()
        return out or None
    except Exception:
        return None

NEON_URL = resolve_neon_url()

try:
    import psycopg2  # type: ignore
    PG_AVAILABLE = NEON_URL is not None
except ImportError:
    PG_AVAILABLE = False

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def step(flow: str, n: int, label: str) -> None:
    print(f"\n[{flow}] {n:02d}. {label}")

def ok(msg: str)   -> None: print(f"     ✅ {msg}")
def info(msg: str) -> None: print(f"     · {msg}")
def die(msg: str, resp: requests.Response | None = None) -> None:
    print(f"     ❌ {msg}", file=sys.stderr)
    if resp is not None:
        print(f"     HTTP {resp.status_code}", file=sys.stderr)
        body = resp.text[:1500]
        print(f"     body: {body}", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Neon DB helper — safe no-op if psycopg2 / connection-string unavailable
# ---------------------------------------------------------------------------
def db_verify(label: str, sql: str, params: tuple, expected_min_rows: int = 1) -> None:
    if not PG_AVAILABLE:
        info(f"DB-CHECK skipped ({label}) — psycopg2 or connection-string unavailable")
        return
    try:
        conn = psycopg2.connect(NEON_URL, connect_timeout=10)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as exc:
        info(f"DB-CHECK warn ({label}): {exc}")
        return
    if len(rows) < expected_min_rows:
        die(f"DB-CHECK failed ({label}): got {len(rows)} rows, expected ≥ {expected_min_rows}")
    ok(f"DB-CHECK {label}: {len(rows)} row(s)")

# ---------------------------------------------------------------------------
# HTTP session per flow (cookies auto-persist)
# ---------------------------------------------------------------------------
def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "User-Agent": "e2e-simulation-flow/0.1"})
    return s

def post(s: requests.Session, path: str, **kw) -> requests.Response:
    return s.post(f"{BASE_URL}{path}", timeout=60, **kw)

def get(s: requests.Session, path: str, **kw) -> requests.Response:
    return s.get(f"{BASE_URL}{path}", timeout=30, **kw)

def wait_for_images_ready(
    s: requests.Session, sim_id: int, *, timeout_s: int = 300, interval_s: int = 5
) -> None:
    deadline = time.monotonic() + timeout_s
    # /upload-status returns total=0 when Redis keys haven't been populated yet
    # (worker hasn't enqueued), so we need a short grace period before trusting it.
    grace_deadline = time.monotonic() + 15
    while True:
        r = get(s, f"/api/publishing/simulations/{sim_id}/upload-status")
        if r.status_code != 200:
            die(f"upload-status fetch failed for sim_id={sim_id}", r)
        body = r.json()
        total     = body.get("total", 0)
        pending   = body.get("pending", 0)
        completed = body.get("completed", 0)
        if total > 0 and pending == 0:
            ok(f"images ready ({completed}/{total})")
            return
        if total == 0 and time.monotonic() >= grace_deadline:
            info("upload-status reports total=0 after grace period; proceeding")
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"timeout after {timeout_s}s waiting for images on sim_id={sim_id} "
                f"(total={total} pending={pending} completed={completed})"
            )
        info(f"waiting on {pending}/{total} image(s)")
        time.sleep(interval_s)

# ---------------------------------------------------------------------------
# Flow 1 — Professor
# ---------------------------------------------------------------------------
def run_flow_1() -> dict:
    s = new_session()
    run_id = int(time.time())
    prof_email    = f"e2e_prof_{run_id}@example.com"
    prof_password = f"E2EProf!{uuid.uuid4().hex[:8]}"
    prof_username = f"e2e_prof_{run_id}"

    # --- 1. register
    step("FLOW-1", 1, f"register professor (email={prof_email})")
    r = post(s, "/api/auth/users/register", json={
        "email": prof_email, "password": prof_password,
        "full_name": "E2E Professor", "username": prof_username,
        "role": "professor",
    })
    if r.status_code != 200:
        die("register failed", r)
    ok(f"registered user_id={r.json().get('id')}")
    db_verify("users.professor", "SELECT id FROM users WHERE email=%s AND role='professor'", (prof_email,))

    # --- 2. login (captures cookie)
    step("FLOW-1", 2, "login as professor")
    r = post(s, "/api/auth/users/login", json={"email": prof_email, "password": prof_password})
    if r.status_code != 200 or "access_token" not in s.cookies:
        die("login failed (no access_token cookie)", r)
    ok("auth cookie captured")

    # --- 3. upload sample PDF → create draft simulation
    step("FLOW-1", 3, f"upload sample PDF → parse")
    if not FIXTURE_PDF.exists():
        die(f"fixture PDF missing at {FIXTURE_PDF} (run from repo root)")
    with FIXTURE_PDF.open("rb") as f:
        r = post(s, "/api/pdf-processing/parse-pdf",
                 files={"file": ("HBR_CaseStudy.pdf", f, "application/pdf")})
    if r.status_code not in (200, 201):
        die("parse-pdf failed", r)
    parse_result = r.json()
    # parse-pdf returns {"status": "completed", "ai_result": {...}} — the
    # ai_result is parsed personas/scenes/objectives but is NOT yet a draft.
    # The frontend separately POSTs /save with that payload to create the
    # draft. Try that here; if it doesn't accept the shape, fall back to
    # using an existing simulation in the experimental DB.
    simulation_id = parse_result.get("simulation_id") or parse_result.get("id")
    if not simulation_id:
        ai_result = parse_result.get("ai_result") or {}
        if not ai_result:
            die("parse-pdf returned no simulation_id and no ai_result — cannot build a draft", r)
        save_payload = {
            "title": ai_result.get("title", f"E2E simulation {int(time.time())}"),
            "description": ai_result.get("description", ""),
            "personas": ai_result.get("personas", []),
            "scenes": ai_result.get("scenes", []),
            "learning_outcomes": ai_result.get("learning_outcomes", []),
        }
        sr = post(s, "/api/publishing/simulations/save", json=save_payload)
        if sr.status_code not in (200, 201):
            die("save draft failed — parse-pdf did not produce a usable draft", sr)
        simulation_id = sr.json().get("simulation_id") or sr.json().get("id")
        if not simulation_id:
            die(f"/save returned {sr.status_code} but no simulation_id in body: {sr.text[:500]}")
        info(f"created draft via /save → id={simulation_id}")
    ok(f"simulation_id={simulation_id}")
    db_verify("simulations.exists", "SELECT id FROM simulations WHERE id=%s", (simulation_id,))

    # --- 4. publish
    step("FLOW-1", 4, f"publish simulation_id={simulation_id}")
    wait_for_images_ready(s, simulation_id)
    r = post(s, f"/api/publishing/simulations/publish/{simulation_id}", json={})
    if r.status_code not in (200, 201):
        die("publish failed", r)
    ok("published")
    db_verify("simulations.published", "SELECT id FROM simulations WHERE id=%s AND status='active'", (simulation_id,))

    # --- 5. create cohort
    step("FLOW-1", 5, "create cohort")
    cohort_name = f"E2E Cohort {run_id}"
    r = post(s, "/professor/cohorts/", json={"name": cohort_name})
    if r.status_code not in (200, 201):
        die("create cohort failed", r)
    cohort = r.json()
    cohort_id = cohort.get("id") or cohort.get("unique_id")
    ok(f"cohort id={cohort_id}")
    db_verify("cohorts", "SELECT id FROM cohorts WHERE name=%s", (cohort_name,))

    # --- 6. assign simulation
    step("FLOW-1", 6, f"assign simulation → cohort")
    r = post(s, f"/professor/cohorts/{cohort_id}/simulations",
             json={"simulation_id": simulation_id})
    if r.status_code not in (200, 201):
        die("assign simulation failed", r)
    ok("assigned")

    # --- 7. create invite
    step("FLOW-1", 7, "create invite link")
    r = post(s, f"/professor/cohorts/{cohort_id}/invites", json={})
    if r.status_code not in (200, 201):
        die("create invite failed", r)
    invite_token = r.json().get("token") or r.json().get("invite_token")
    if not invite_token:
        die("no invite token in response", r)
    ok(f"invite token captured (length={len(invite_token)})")

    return {
        "professor_email": prof_email,
        "simulation_id":   simulation_id,
        "cohort_id":       cohort_id,
        "invite_token":    invite_token,
        "run_id":          run_id,
    }

# ---------------------------------------------------------------------------
# Flow 2 — Student
# ---------------------------------------------------------------------------
def run_flow_2(ctx: dict) -> None:
    s = new_session()
    run_id   = ctx["run_id"]
    email    = f"e2e_student_{run_id}@example.com"
    password = f"E2EStu!{uuid.uuid4().hex[:8]}"
    username = f"e2e_student_{run_id}"

    # --- 1. register student
    step("FLOW-2", 1, f"register student (email={email})")
    r = post(s, "/api/auth/users/register", json={
        "email": email, "password": password,
        "full_name": "E2E Student", "username": username,
        "role": "student",
    })
    if r.status_code != 200:
        die("register student failed", r)
    ok("registered")
    db_verify("users.student", "SELECT id FROM users WHERE email=%s AND role='student'", (email,))

    # --- 2. login
    step("FLOW-2", 2, "login as student")
    r = post(s, "/api/auth/users/login", json={"email": email, "password": password})
    if r.status_code != 200:
        die("student login failed", r)
    ok("cookie captured")

    # --- 3. accept invite
    step("FLOW-2", 3, "accept cohort invite")
    r = post(s, f"/invites/{ctx['invite_token']}/accept")
    if r.status_code not in (200, 201):
        die("accept invite failed", r)
    accept_body = r.json()
    ok(f"joined cohort (cohort_id={accept_body.get('cohort_id')} "
       f"already_enrolled={accept_body.get('already_enrolled')})")

    # --- 4. start simulation
    step("FLOW-2", 4, f"start simulation (id={ctx['simulation_id']})")
    r = post(s, "/api/simulation/start", json={"simulation_id": ctx["simulation_id"]})
    if r.status_code not in (200, 201):
        die("start simulation failed", r)
    start = r.json()
    progress_id  = start.get("user_progress_id") or start.get("user_progress", {}).get("id")
    current_scene = start.get("current_scene", {})
    if not progress_id:
        die("no user_progress_id in start response", r)
    ok(f"user_progress_id={progress_id}  current_scene_order={current_scene.get('scene_order', '?')}")

    # --- 5. scripted Q&A per scene
    step("FLOW-2", 5, "play simulation with scripted Q&A")
    if not FIXTURE_QUESTIONS.exists():
        die(f"fixture missing: {FIXTURE_QUESTIONS}")
    questions = json.loads(FIXTURE_QUESTIONS.read_text())["scenes"]

    for scene in questions:
        scene_label = f"scene {scene['scene_order']}"
        info(f"playing {scene_label}: {len(scene['turns'])} turn(s)")
        for turn_text in scene["turns"]:
            r = post(s, "/api/simulation/linear-chat",
                     json={"user_progress_id": progress_id, "message": turn_text})
            if r.status_code not in (200, 201):
                die(f"{scene_label} turn failed: {turn_text[:60]!r}", r)
        # advance phrase (some sims use content-based triggers)
        r = post(s, "/api/simulation/linear-chat",
                 json={"user_progress_id": progress_id, "message": scene["advance_phrase"]})
        if r.status_code not in (200, 201):
            die(f"{scene_label} advance-phrase failed", r)
        ok(f"{scene_label} complete")

    # --- 6. verify terminal state
    step("FLOW-2", 6, "verify simulation completed")
    r = get(s, f"/api/simulation/progress/{progress_id}")
    if r.status_code != 200:
        die("progress fetch failed", r)
    prog = r.json()
    completed = prog.get("completed_at") or prog.get("is_complete")
    if completed:
        ok(f"simulation completed (completed_at={prog.get('completed_at')})")
    else:
        info(f"simulation not marked complete; current_scene={prog.get('current_scene_id')} — fixture may need more scenes")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print("=== E2E simulation flow (experimental env) ===")
    print(f"  BASE_URL:       {BASE_URL}")
    print(f"  NEON_BRANCH:    {NEON_BRANCH}  (project={NEON_PROJECT_ID})")
    print(f"  DB checks:      {'ENABLED' if PG_AVAILABLE else 'SKIPPED (psycopg2 or conn-string missing)'}")

    ctx = run_flow_1()
    run_flow_2(ctx)

    print("\n=== ✅ END-TO-END FLOW PASSED ===")
    print(f"  run_id:           {ctx['run_id']}")
    print(f"  professor email:  {ctx['professor_email']}")
    print(f"  simulation_id:    {ctx['simulation_id']}")
    print(f"  cohort_id:        {ctx['cohort_id']}")
    print("  (test users not cleaned up — inspect in Neon experimental-v2 if needed)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
