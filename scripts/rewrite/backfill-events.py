#!/usr/bin/env python3
"""Backfill Ralph-pipeline events from historical log files.

The loop didn't emit events before PR-B landed, but it left behind
rich master logs at `scripts/rewrite/logs/rewrite_*.log`. This script
parses those logs for phase-transition signatures and POSTs synthetic
events to the admin dashboard's ingest endpoint so the grid has data
from the very first run the dashboard sees.

Idempotent enough for overnight use: the dashboard's /event endpoint
accepts duplicates — if you run this twice you'll see double rows for
the same transition. To avoid that, back up + truncate the
`ralph_pipeline_events` table before a fresh backfill, or use the
optional `--since` flag to only re-ingest recent runs.

Usage:
    # env vars (can also live in backend/.env)
    export RALPH_EVENT_URL=https://backend-experimental-246c.up.railway.app
    export RALPH_EVENT_TOKEN=<bearer>

    python3 scripts/rewrite/backfill-events.py                    # all logs
    python3 scripts/rewrite/backfill-events.py --dry-run          # parse + print, no POST
    python3 scripts/rewrite/backfill-events.py --since 2026-04-13 # one day
    python3 scripts/rewrite/backfill-events.py --file <one.log>   # just that log

Exit 0 on success; 2 on config error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "scripts" / "rewrite" / "logs"


# ── .env loader (same keys the loop's config.sh looks for) ────────────────
def _load_env() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for candidate in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in out:
                out[k] = v
    return out


ENV = _load_env()
RALPH_EVENT_URL = os.environ.get("RALPH_EVENT_URL", ENV.get("RALPH_EVENT_URL", ""))
RALPH_EVENT_TOKEN = os.environ.get("RALPH_EVENT_TOKEN", ENV.get("RALPH_EVENT_TOKEN", ""))


# ── log parser ────────────────────────────────────────────────────────────
# Matches lines like "[14:37:26]   picked: #430  phase-0.01  ..."
# or "[14:49:27]   PR opened: #457" etc. The loop logs timestamp as HH:MM:SS
# so we reconstruct the date from the log filename.
LINE_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s+(.*)$")

# Phase markers we know how to derive an event from. Order matters — first match wins per line.
# Each entry: (regex, phase, status, detail_group_or_None, context_json_fn)
PHASE_MARKERS = [
    (re.compile(r"picked:\s+#(\d+)\s+(phase-\d+(?:\.\d+)?)"), None, None, None, None),  # context only
    (re.compile(r"→ invoking Claude for implementation"), "A-implement", "started", None, None),
    (re.compile(r"PR opened:\s*#?(\d+)"), "A-implement", "passed", None, None),
    (re.compile(r"no PR produced"), "A-implement", "failed", "no PR produced", None),
    (re.compile(r"waiting for first CodeRabbit"), "B-review", "started", None, lambda m: {"round": 1}),
    (re.compile(r"round (\d+)/\d+ — addressing CR feedback"), "B-review", "started", None, lambda m: {"round": int(m.group(1))}),
    (re.compile(r"CR approved PR"), "B-review", "passed", None, None),
    (re.compile(r"no new CR comments after push — treating as resolved"), "B-review", "passed", "no new feedback", None),
    (re.compile(r"hit CR_MAX_ROUNDS"), "B-review", "failed", "hit CR_MAX_ROUNDS", None),
    (re.compile(r"→ invoking Claude for testing"), "C-testing", "started", None, None),
    (re.compile(r"ALL_TESTS_PASSED"), "C-testing", "passed", None, None),
    (re.compile(r"tests failed — leaving PR"), "C-testing", "failed", "tests did not report pass", None),
    (re.compile(r"^\s*TESTS_FAILED:(.+)"), "C-testing", "failed", 1, None),
    (re.compile(r"polling CI "), "D-merge", "started", None, None),
    (re.compile(r"CI green — merging"), "D-merge", "passed", None, None),
    (re.compile(r"CI not green after polls"), "D-merge", "failed", "CI not green after polls", None),
    (re.compile(r"Canny post ok"), "E-canny", "passed", None, None),
    (re.compile(r"Canny.*(skipping|env vars not set)"), "E-canny", "skipped", "env not configured", None),
]


@dataclass
class ParsedEvent:
    ticket_id: str
    iteration: int
    loop_run_id: str
    pr_number: Optional[int]
    phase: str
    status: str
    detail: Optional[str] = None
    duration_sec: Optional[int] = None
    context: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "ticket_id":    self.ticket_id,
            "iteration":    max(1, self.iteration),
            "loop_run_id":  self.loop_run_id,
            "pr_number":    self.pr_number,
            "phase":        self.phase,
            "status":       self.status,
            "detail":       self.detail,
            "duration_sec": self.duration_sec,
            "context":      self.context,
        }


def parse_log(path: Path) -> List[ParsedEvent]:
    """Pull phase events out of one master log."""
    # Log filename encodes the date as YYYYMMDD_HHMMSS.
    m = re.search(r"rewrite_(\d{8}_\d{6})\.log$", path.name)
    if not m:
        return []
    loop_run_id = m.group(1)
    log_date = datetime.strptime(loop_run_id, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)

    events: List[ParsedEvent] = []
    current_ticket = "phase-0.0"
    current_iter = 0
    current_pr: Optional[int] = None

    for raw in path.read_text(errors="replace").splitlines():
        m = LINE_RE.match(raw)
        if not m:
            continue
        ts_str, body = m.groups()
        hh, mm, ss = (int(x) for x in ts_str.split(":"))
        # Rebuild absolute time from filename date + log-line HH:MM:SS.
        ts = log_date.replace(hour=hh, minute=mm, second=ss)
        # If we've crossed midnight within the log (HH regressed), bump date.
        if events and ts < (events[-1].created_at or ts):
            ts = ts.replace(day=ts.day + 1) if ts.day < 28 else ts  # cheap heuristic

        # Track ticket + iteration + PR from context lines.
        mi = re.search(r"─── iteration (\d+)/\d+ ───", body)
        if mi:
            current_iter = int(mi.group(1))
            continue

        mp = re.search(r"picked: #(\d+)\s+(phase-\d+(?:\.\d+)?)", body)
        if mp:
            # NOTE: the log prints ticket_id like "phase-0.01". Normalize to "phase-0.1".
            current_pr = None  # new ticket = new PR forthcoming
            tid = mp.group(2)
            tid = re.sub(r"phase-(\d+)\.0(\d)", r"phase-\1.\2", tid)
            current_ticket = tid
            continue

        mpr = re.search(r"PR opened: ?#?(\d+)", body)
        if mpr:
            current_pr = int(mpr.group(1))

        # Scan phase markers.
        for regex, phase, status, detail_spec, ctx_fn in PHASE_MARKERS:
            mm2 = regex.search(body)
            if not mm2:
                continue
            if phase is None:
                continue  # context-only markers already handled above
            detail = None
            if detail_spec is not None:
                if isinstance(detail_spec, int):
                    detail = mm2.group(detail_spec).strip()
                else:
                    detail = detail_spec
            ctx = ctx_fn(mm2) if ctx_fn else None
            events.append(ParsedEvent(
                ticket_id=current_ticket,
                iteration=current_iter or 1,
                loop_run_id=loop_run_id,
                pr_number=current_pr,
                phase=phase,
                status=status,
                detail=detail,
                context=ctx,
                created_at=ts,
            ))
            break
    return events


# ── POST to /event ────────────────────────────────────────────────────────
def post_event(payload: Dict[str, Any]) -> bool:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{RALPH_EVENT_URL.rstrip('/')}/api/admin/ralph-pipeline/event",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {RALPH_EVENT_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 201, 202)
    except Exception as exc:
        print(f"  WARN: POST failed for {payload['ticket_id']}/{payload['phase']}: {exc}",
              file=sys.stderr)
        return False


# ── main ──────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="parse + print, no POST")
    ap.add_argument("--since", help="YYYY-MM-DD — only logs modified on/after this date")
    ap.add_argument("--file", help="single log file (overrides --since + auto-discovery)")
    args = ap.parse_args()

    if not args.dry_run:
        if not RALPH_EVENT_URL or not RALPH_EVENT_TOKEN:
            print("ERROR: RALPH_EVENT_URL and RALPH_EVENT_TOKEN must be set "
                  "(env vars or .env / backend/.env)", file=sys.stderr)
            return 2

    # Gather input logs.
    if args.file:
        logs = [Path(args.file)]
    else:
        logs = sorted(LOG_DIR.glob("rewrite_*.log"))
        if args.since:
            cutoff = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            logs = [p for p in logs
                    if datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc) >= cutoff]
    if not logs:
        print("No logs to backfill.", file=sys.stderr)
        return 0

    total_events = 0
    total_posted = 0
    for p in logs:
        events = parse_log(p)
        total_events += len(events)
        print(f"  {p.name}: {len(events)} events")
        if args.dry_run:
            for e in events[:5]:
                print(f"    {e.created_at} {e.ticket_id} iter{e.iteration} "
                      f"{e.phase} {e.status} pr={e.pr_number}")
            if len(events) > 5:
                print(f"    … +{len(events) - 5} more")
            continue
        for e in events:
            if post_event(e.to_payload()):
                total_posted += 1

    mode = "parsed (dry-run)" if args.dry_run else "posted"
    print(f"\nDone. {total_events} events {mode}; "
          f"{total_posted} POST succeeded"
          + (" (run without --dry-run to ingest)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
