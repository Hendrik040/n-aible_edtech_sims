#!/usr/bin/env python3
"""One-shot migration: retarget the rewrite-agent-sdk track onto ralph-looped.

Actions (in order):
  1. Pass A — create 22 new issues with bodies targeting `ralph-looped`,
     @coderabbitai plan + @claude trailer, "Depends on" populated with
     placeholder `TBD — will be rewritten`.
  2. Pass B — edit each new issue body to swap the TBD placeholder for
     the real dependency numbers (DAG preserved from #407..#428).
  3. Close each old issue (#407..#428) with a closing comment that
     points to its replacement.

Idempotent: re-running after partial completion skips already-processed
items by checking the state of each source issue (still open?) and the
title of each target (new issue with that title already exists?).

Run once:
    python scripts/rewrite/migrate-to-ralph-looped.py [--dry-run] [--yes]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BREAKDOWN = REPO_ROOT / "plan" / "REWRITE_BREAKDOWN.md"
REPO = "Hendrik040/n-aible_edtech_sims"
OLD_ISSUE_RANGE = range(407, 429)  # 407..428 inclusive

LABEL_PRIMARY = "rewrite-agent-sdk"
LABEL_TYPE = "type-rewrite"
ANCHOR_BRANCH = "ralph-looped-rewrite-agent-sdk"
TARGET_BRANCH = "ralph-looped"
FEATURE_PREFIX = "ralph-looped-rewrite"  # feature branches live here

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
        return "phase-" + self.id.split("-", 1)[1].split(".", 1)[0]

    @property
    def issue_title(self) -> str:
        return f"[{LABEL_PRIMARY}] {self.id}: {self.title}"

    @property
    def slug(self) -> str:
        base = self.title.lower()
        base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        parts = base.split("-")
        # Drop filler words to keep slugs short.
        skip = {"the", "a", "an", "py", "into", "for", "with", "and", "or", "of"}
        parts = [p for p in parts if p not in skip]
        slug = "-".join(parts)[:40].strip("-")
        return slug or self.id


def parse_breakdown() -> list[Ticket]:
    text = BREAKDOWN.read_text(encoding="utf-8")
    tickets: list[Ticket] = []
    current: Ticket | None = None
    key: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal key, buf
        if current is None or key is None:
            key, buf = None, []
            return
        val = " ".join(s.strip() for s in buf).strip()
        if key == "depends_on":
            inner = val.strip()
            if inner in ("", "[]"):
                current.depends_on = []
            else:
                inner = inner.strip("[]")
                current.depends_on = [p.strip() for p in inner.split(",") if p.strip()]
        elif hasattr(current, key):
            setattr(current, key, val)
        key, buf = None, []

    for line in text.splitlines():
        m = TICKET_HEADER_RE.match(line)
        if m:
            flush()
            if current is not None:
                tickets.append(current)
            current = Ticket(id=m.group(1), title=m.group(2).strip())
            continue
        if current is None:
            continue
        kv = KV_RE.match(line)
        if kv:
            flush()
            key = kv.group(1)
            buf = [kv.group(2)]
            continue
        if key is not None:
            stripped = line.strip()
            if not stripped or line.startswith("### ") or line.startswith("## "):
                flush()
                continue
            buf.append(stripped)
    flush()
    if current is not None:
        tickets.append(current)
    return tickets


def gh(*args: str, check: bool = True, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        check=check,
        text=True,
        capture_output=True,
        input=input,
    )


def existing_new_issue(title: str) -> int | None:
    """Find a new-generation issue by title (must be outside the old range)."""
    out = gh(
        "issue", "list",
        "--repo", REPO,
        "--label", LABEL_PRIMARY,
        "--state", "all",
        "--limit", "200",
        "--json", "number,title",
    ).stdout
    for row in json.loads(out or "[]"):
        if row.get("title") == title and int(row["number"]) not in OLD_ISSUE_RANGE:
            return int(row["number"])
    return None


def render_body(ticket: Ticket, dep_numbers: dict[str, int], placeholder_ok: bool) -> str:
    if ticket.depends_on:
        dep_lines = []
        for dep_id in ticket.depends_on:
            num = dep_numbers.get(dep_id)
            if num:
                dep_lines.append(f"- #{num} ({dep_id})")
            elif placeholder_ok:
                dep_lines.append(f"- TBD — {dep_id} (will be rewritten in pass B)")
            else:
                raise ValueError(f"dependency {dep_id} unresolved for {ticket.id}")
        deps_block = "\n".join(dep_lines)
    else:
        deps_block = "_None — ready to pick up immediately._"

    feature_branch = f"{FEATURE_PREFIX}/{ticket.id}-{ticket.slug}"

    return f"""<!-- Generated by scripts/rewrite/migrate-to-ralph-looped.py from plan/REWRITE_BREAKDOWN.md -->
<!-- ticket-id: {ticket.id} -->

## Ticket: `{ticket.id}` — {ticket.title}

**Target branch:** `{TARGET_BRANCH}` (feature branch forks off `{ANCHOR_BRANCH}`)

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

See `plan/REWRITE_BREAKDOWN.md` on `claude/restructure-workflow-branching-jz8s0`
for the full ticket graph. The Ralph loop picks up tickets once upstream
dependencies are merged into `{TARGET_BRANCH}`. Feature branch for this
ticket: `{feature_branch}`.

---

@coderabbitai plan

@claude please start a session to implement this ticket. Fork `{feature_branch}` off `{ANCHOR_BRANCH}` and open the PR against `{TARGET_BRANCH}`.
"""


def create_issue(ticket: Ticket, body: str, dry_run: bool) -> int | None:
    labels = [LABEL_PRIMARY, ticket.phase_label, LABEL_TYPE]
    if dry_run:
        print(f"  [dry-run] create: {ticket.issue_title}")
        return None
    args = ["issue", "create",
            "--repo", REPO,
            "--title", ticket.issue_title,
            "--body", body]
    for lbl in labels:
        args.extend(["--label", lbl])
    try:
        out = gh(*args).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"  ERROR: gh issue create failed: {exc.stderr}", file=sys.stderr)
        return None
    m = re.search(r"/issues/(\d+)", out)
    return int(m.group(1)) if m else None


def update_issue_body(issue_num: int, body: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] edit #{issue_num} body")
        return
    gh("issue", "edit", str(issue_num), "--repo", REPO, "--body-file", "-", input=body)


def close_issue(issue_num: int, comment: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] close #{issue_num} with comment")
        return
    gh("issue", "comment", str(issue_num), "--repo", REPO, "--body", comment)
    gh("issue", "close", str(issue_num), "--repo", REPO, "--reason", "not planned")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true",
                    help="Skip the are-you-sure prompt (CI/scripting).")
    args = ap.parse_args()

    tickets = parse_breakdown()
    if len(tickets) != 22:
        print(f"ERROR: expected 22 tickets, parsed {len(tickets)}", file=sys.stderr)
        return 2

    # --- discover the old issues by ticket id (from titles) -----------------
    print("Discovering old issues #407..#428 ...")
    old_by_tid: dict[str, int] = {}
    out = gh("issue", "list",
             "--repo", REPO,
             "--label", LABEL_PRIMARY,
             "--state", "all",
             "--limit", "200",
             "--json", "number,title,state").stdout
    for row in json.loads(out or "[]"):
        n = int(row["number"])
        if n not in OLD_ISSUE_RANGE:
            continue
        m = re.search(r"phase-\d+(?:\.\d+)?", row["title"])
        if m:
            old_by_tid[m.group(0)] = n
    for t in tickets:
        if t.id not in old_by_tid:
            print(f"WARNING: old issue for {t.id} not found in #{OLD_ISSUE_RANGE.start}..", file=sys.stderr)

    print(f"  found {len(old_by_tid)} old issues")

    if not args.yes and not args.dry_run:
        print("\nAbout to:")
        print(f"  1. Create 22 NEW issues with @claude triggers targeting {TARGET_BRANCH}")
        print(f"  2. Rewrite Depends-on in each new issue with real #s")
        print(f"  3. Close {len(old_by_tid)} OLD issues (#407..#428) with Replaced-by pointers")
        ans = input("Proceed? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted.")
            return 1

    # --- Pass A — create new issues with placeholder deps -------------------
    print("\n=== Pass A: creating new issues ===")
    new_by_tid: dict[str, int] = {}
    for t in tickets:
        print(f"\n--- {t.id}: {t.title} ---")
        # Idempotency — if a new issue with this title already exists, reuse.
        existing = existing_new_issue(t.issue_title)
        if existing is not None:
            print(f"  found existing new issue #{existing} — reusing")
            new_by_tid[t.id] = existing
            continue
        body = render_body(t, new_by_tid, placeholder_ok=True)
        num = create_issue(t, body, args.dry_run)
        if num is not None:
            print(f"  created #{num}")
            new_by_tid[t.id] = num
        elif args.dry_run:
            # assign a synthetic number so downstream dep-rendering has something
            new_by_tid[t.id] = 10000 + len(new_by_tid)
        time.sleep(0.5)  # be polite to the API

    # --- Pass B — rewrite Depends-on with real numbers ---------------------
    print("\n=== Pass B: rewriting Depends-on with real issue numbers ===")
    for t in tickets:
        num = new_by_tid.get(t.id)
        if num is None:
            print(f"  {t.id}: no new issue — skipping")
            continue
        if not t.depends_on:
            print(f"  {t.id} (#{num}): no deps — skipping")
            continue
        body = render_body(t, new_by_tid, placeholder_ok=False)
        print(f"  updating #{num} ({t.id}) with deps {t.depends_on}")
        update_issue_body(num, body, args.dry_run)
        time.sleep(0.3)

    # --- Pass C — close old issues with Replaced-by pointers ---------------
    print("\n=== Pass C: closing old issues with Replaced-by pointers ===")
    for t in tickets:
        old = old_by_tid.get(t.id)
        new = new_by_tid.get(t.id)
        if old is None:
            continue
        if new is None:
            print(f"  {t.id} (#{old}): no new issue assigned — leaving open")
            continue
        comment = (
            f"Closing — this track is being retargeted off `rewrite/agent-sdk` onto "
            f"`ralph-looped` so work lands incrementally on top of the active "
            f"ralph-looped branch instead of a big-bang cutover. The CodeRabbit "
            f"plan above is preserved for reference.\n\n"
            f"Replaced by #{new}."
        )
        print(f"  closing #{old} → replaced by #{new}")
        close_issue(old, comment, args.dry_run)
        time.sleep(0.3)

    # --- final map ---------------------------------------------------------
    print("\n--- Old → New mapping ---")
    for t in tickets:
        print(f"  {t.id:<12} #{old_by_tid.get(t.id, '?')} → #{new_by_tid.get(t.id, '?')}")

    # Write the mapping out for REWRITE_BREAKDOWN.md to consume.
    mapping_path = REPO_ROOT / "scripts" / "rewrite" / "logs" / "old-to-new-mapping.json"
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(json.dumps(
        {t.id: {"old": old_by_tid.get(t.id), "new": new_by_tid.get(t.id),
                "title": t.title, "slug": t.slug,
                "feature_branch": f"{FEATURE_PREFIX}/{t.id}-{t.slug}",
                "depends_on": t.depends_on}
         for t in tickets},
        indent=2,
    ))
    print(f"\nMapping written to {mapping_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
