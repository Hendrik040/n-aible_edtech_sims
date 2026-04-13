#!/usr/bin/env python3
"""Create GitHub issues from plan/REWRITE_BREAKDOWN.md.

One issue per `### phase-X.Y:` block. Labels: `rewrite-agent-sdk`,
`phase-N`, `type-rewrite`. Body is rendered from the parsed spec and is
exactly what CodeRabbit sees when it plans, so the plan stays grounded
in the same constraints the verifier enforces.

Idempotent: re-running finds existing issues by title and skips
creation. The CodeRabbit `@coderabbitai plan` trigger uses the same
"already has a plan comment?" heuristic as the legacy ralph loop so we
never double-trigger.

Usage:
    python scripts/rewrite/create-issues.py [--dry-run]
                                            [--only phase-X.Y[,phase-...]]
                                            [--skip-plan]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BREAKDOWN_PATH = REPO_ROOT / "plan" / "REWRITE_BREAKDOWN.md"
LABEL_PRIMARY = "rewrite-agent-sdk"
LABEL_TYPE = "type-rewrite"
TARGET_BRANCH = "rewrite/agent-sdk"

TICKET_HEADER_RE = re.compile(r"^### (phase-\d+(?:\.\d+)?): (.+)$")
KV_RE = re.compile(r"^- \*\*(\w+)\*\*:\s*(.*)$")


@dataclass
class Ticket:
    id: str
    title: str
    depends_on: list[str] = field(default_factory=list)
    branch_prefix: str = ""
    files: str = ""
    scope: str = ""
    unit_tests_required: str = "none"
    contract_tests_required: str = "none"
    verification: str = ""
    non_goals: str = ""

    @property
    def phase_label(self) -> str:
        # phase-2.7 → phase-2
        return "phase-" + self.id.split("-", 1)[1].split(".", 1)[0]

    @property
    def issue_title(self) -> str:
        return f"[{LABEL_PRIMARY}] {self.id}: {self.title}"


def parse_breakdown(path: Path) -> list[Ticket]:
    text = path.read_text(encoding="utf-8")
    tickets: list[Ticket] = []
    current: Ticket | None = None
    current_key: str | None = None
    buffer: list[str] = []

    def flush_key() -> None:
        nonlocal current_key, buffer
        if current is None or current_key is None:
            current_key = None
            buffer = []
            return
        value = " ".join(s.strip() for s in buffer).strip()
        if current_key == "depends_on":
            inner = value.strip()
            if inner in ("", "[]"):
                current.depends_on = []
            else:
                inner = inner.strip("[]")
                current.depends_on = [
                    part.strip() for part in inner.split(",") if part.strip()
                ]
        elif hasattr(current, current_key):
            setattr(current, current_key, value)
        current_key = None
        buffer = []

    for raw_line in text.splitlines():
        header = TICKET_HEADER_RE.match(raw_line)
        if header:
            flush_key()
            if current is not None:
                tickets.append(current)
            current = Ticket(id=header.group(1), title=header.group(2).strip())
            continue
        if current is None:
            continue
        kv = KV_RE.match(raw_line)
        if kv:
            flush_key()
            current_key = kv.group(1)
            buffer = [kv.group(2)]
            continue
        if current_key is not None:
            stripped = raw_line.strip()
            # Blank line or a new markdown section ends the current value.
            if not stripped or raw_line.startswith("### ") or raw_line.startswith("## "):
                flush_key()
                continue
            buffer.append(stripped)

    flush_key()
    if current is not None:
        tickets.append(current)
    return tickets


def gh(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        check=check,
        text=True,
        capture_output=capture,
    )


def find_existing_issue(title: str) -> int | None:
    # Search across open + closed so reruns on a partially-seeded tracker
    # don't create duplicates.
    try:
        out = gh(
            "issue", "list",
            "--label", LABEL_PRIMARY,
            "--state", "all",
            "--limit", "200",
            "--json", "number,title",
        ).stdout
    except subprocess.CalledProcessError as exc:
        print(f"gh issue list failed: {exc.stderr}", file=sys.stderr)
        raise
    for row in json.loads(out or "[]"):
        if row.get("title") == title:
            return int(row["number"])
    return None


def has_coderabbit_plan(issue_num: int) -> bool:
    # Matches the check used by the legacy ralph loop (`Coding Plan` etc).
    try:
        out = gh(
            "api", f"repos/:owner/:repo/issues/{issue_num}/comments",
            "--jq",
            '[.[] | select(.user.login | startswith("coderabbitai")) '
            '| select(.body | test("Coding Plan|## Summary|Implementation Steps"; "i"))] | length',
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return False
    try:
        return int(out) > 0
    except ValueError:
        return False


def ensure_labels(labels: set[str]) -> None:
    try:
        out = gh("label", "list", "--limit", "200", "--json", "name").stdout
    except subprocess.CalledProcessError:
        return
    existing = {row["name"] for row in json.loads(out or "[]")}
    for lbl in sorted(labels - existing):
        try:
            gh("label", "create", lbl, "--color", "0E8A16")
            print(f"  created label: {lbl}")
        except subprocess.CalledProcessError as exc:
            print(f"  WARN: could not create label {lbl}: {exc.stderr}", file=sys.stderr)


def render_body(ticket: Ticket, dep_numbers: dict[str, int]) -> str:
    if ticket.depends_on:
        dep_lines = []
        for dep_id in ticket.depends_on:
            num = dep_numbers.get(dep_id)
            if num:
                dep_lines.append(f"- #{num} ({dep_id})")
            else:
                dep_lines.append(f"- {dep_id} (issue not yet created)")
        deps_block = "\n".join(dep_lines)
    else:
        deps_block = "_None — ready to pick up immediately._"

    return f"""<!-- Generated by scripts/rewrite/create-issues.py from plan/REWRITE_BREAKDOWN.md -->
<!-- ticket-id: {ticket.id} -->

## Ticket: `{ticket.id}` — {ticket.title}

**Target branch:** `{TARGET_BRANCH}` (NOT `production-v3`)

### Depends on
{deps_block}

### Scope
{ticket.scope}

### Files this ticket may touch
`{ticket.files}`

### Unit tests required
{ticket.unit_tests_required}

### Contract tests required
{ticket.contract_tests_required}

### Verification (merge gate)
{ticket.verification}

### Non-goals
{ticket.non_goals or "_None specified._"}

---

_This issue is part of the Claude Agent SDK rewrite track. See
`plan/REWRITE_BREAKDOWN.md` for the full ticket graph. The loop at
`scripts/rewrite/ralph-rewrite-loop.sh` picks up tickets once all
upstream dependencies are merged into `{TARGET_BRANCH}`._
"""


def create_issue(ticket: Ticket, body: str, dry_run: bool) -> int | None:
    labels = [LABEL_PRIMARY, ticket.phase_label, LABEL_TYPE]
    if dry_run:
        print(f"  [dry-run] would create issue:")
        print(f"    title:  {ticket.issue_title}")
        print(f"    labels: {','.join(labels)}")
        return None
    args = ["issue", "create",
            "--title", ticket.issue_title,
            "--body", body]
    for lbl in labels:
        args.extend(["--label", lbl])
    try:
        out = gh(*args).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"  ERROR: gh issue create failed: {exc.stderr}", file=sys.stderr)
        return None
    # `gh issue create` prints the URL; extract the number off the end.
    m = re.search(r"/issues/(\d+)", out)
    return int(m.group(1)) if m else None


def trigger_plan(issue_num: int, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] would post '@coderabbitai plan' on #{issue_num}")
        return
    try:
        gh("issue", "comment", str(issue_num), "--body", "@coderabbitai plan")
        print(f"  triggered @coderabbitai plan on #{issue_num}")
    except subprocess.CalledProcessError as exc:
        print(f"  WARN: could not trigger plan on #{issue_num}: {exc.stderr}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse + print but don't touch GitHub.")
    ap.add_argument("--only", default="",
                    help="Comma-separated ticket ids (phase-X.Y) to process; "
                         "default is all.")
    ap.add_argument("--skip-plan", action="store_true",
                    help="Don't post @coderabbitai plan comments.")
    args = ap.parse_args()

    if not BREAKDOWN_PATH.exists():
        print(f"ERROR: {BREAKDOWN_PATH} not found", file=sys.stderr)
        return 2

    tickets = parse_breakdown(BREAKDOWN_PATH)
    if not tickets:
        print("ERROR: parsed zero tickets — check the breakdown file format",
              file=sys.stderr)
        return 2

    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        tickets = [t for t in tickets if t.id in wanted]
        if not tickets:
            print(f"ERROR: --only filter '{args.only}' matched no tickets",
                  file=sys.stderr)
            return 2

    print(f"Parsed {len(tickets)} ticket(s) from {BREAKDOWN_PATH.relative_to(REPO_ROOT)}")

    if not args.dry_run:
        labels_needed = {LABEL_PRIMARY, LABEL_TYPE}
        labels_needed.update(t.phase_label for t in tickets)
        ensure_labels(labels_needed)

    dep_numbers: dict[str, int] = {}
    if not args.dry_run:
        # First pass: discover existing issues so dependency links resolve
        # correctly even when this is a fresh run with partial creation.
        for ticket in tickets:
            existing = find_existing_issue(ticket.issue_title)
            if existing is not None:
                dep_numbers[ticket.id] = existing

    created: list[tuple[str, int]] = []
    for ticket in tickets:
        print(f"\n=== {ticket.id}: {ticket.title} ===")

        existing = dep_numbers.get(ticket.id)
        if existing is None and not args.dry_run:
            existing = find_existing_issue(ticket.issue_title)

        body = render_body(ticket, dep_numbers)

        if existing is not None:
            print(f"  existing issue: #{existing} (skipping creation)")
            issue_num = existing
        else:
            issue_num = create_issue(ticket, body, args.dry_run)
            if issue_num is not None:
                dep_numbers[ticket.id] = issue_num
                created.append((ticket.id, issue_num))
                print(f"  created #{issue_num}")

        if issue_num is None:
            continue

        if args.skip_plan:
            continue
        if args.dry_run:
            trigger_plan(issue_num, dry_run=True)
            continue
        if has_coderabbit_plan(issue_num):
            print(f"  CodeRabbit plan already exists on #{issue_num} — skipping trigger")
        else:
            trigger_plan(issue_num, dry_run=False)

    print("\n--- Dependency map ---")
    for ticket in tickets:
        num = dep_numbers.get(ticket.id)
        num_str = f"#{num}" if num else "(not created)"
        if ticket.depends_on:
            deps = ", ".join(
                f"#{dep_numbers[d]}" if d in dep_numbers else d
                for d in ticket.depends_on
            )
            print(f"  {ticket.id:<12} {num_str:<8} needs {deps}")
        else:
            print(f"  {ticket.id:<12} {num_str:<8} (root)")

    print(f"\nDone. {len(created)} issue(s) created this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
