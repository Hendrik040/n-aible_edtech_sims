#!/usr/bin/env python3
"""Phase E — post a Canny changelog entry for a merged PR.

Triggered by ralph-rewrite-loop.sh only on successful `gh pr merge
--squash`. Generates a non-technical summary via claude --print, POSTs
it to the Canny board configured in .env (same board as user feedback;
dashboard filters via the title prefix), and comments the Canny URL
back onto the GitHub PR so the admin dashboard can render both sides
of the link.

Args:
    --pr <number>       merged PR number (required)
    --ticket <id>       phase-X.Y ticket id (required)
    --issue <number>    issue number to reference (optional, derived from PR body if omitted)
    --dry-run           render + print; don't POST or comment

Exit codes:
    0  — Canny post created + PR linkback comment posted
    1  — Canny disabled (no env vars) — loop continues, no failure
    2  — hard failure (API error, claude failed, etc.)

Security:
    - reads CANNY_API_KEY / CANNY_BOARD_ID / CANNY_ADMIN_ID from env
    - never prints, logs, or persists those values
    - GitHub `gh` CLI handles its own auth
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent
PROMPT_FILE   = RESOURCES_DIR / "prompts" / "post-to-canny.md"

CANNY_API_KEY   = os.environ.get("CANNY_API_KEY", "")
CANNY_BOARD_ID  = os.environ.get("CANNY_BOARD_ID", "")
CANNY_ADMIN_ID  = os.environ.get("CANNY_ADMIN_ID", "")
CANNY_PREFIX    = os.environ.get("CANNY_TITLE_PREFIX", "[rewrite]")
GH_REPO         = os.environ.get("GH_REPO", "Hendrik040/n-aible_edtech_sims")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[post-to-canny] {msg}")

def die(msg: str, code: int = 2) -> None:
    print(f"[post-to-canny] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def canny_enabled() -> bool:
    return bool(CANNY_API_KEY and CANNY_BOARD_ID and CANNY_ADMIN_ID)

def gh_json(*args: str) -> dict | list:
    try:
        out = subprocess.run(
            ["gh", *args], check=True, capture_output=True, text=True, timeout=30,
        ).stdout
        return json.loads(out) if out.strip() else {}
    except subprocess.CalledProcessError as e:
        die(f"gh failed: {e.stderr.strip()}")
    except json.JSONDecodeError:
        die(f"gh returned non-JSON: {out[:200]!r}")

def fetch_pr_context(pr: int) -> dict:
    pr_data = gh_json(
        "pr", "view", str(pr), "--repo", GH_REPO,
        "--json", "title,body,author,files,additions,deletions,mergedAt",
    )
    files = pr_data.get("files") or []
    return {
        "title":    pr_data.get("title", ""),
        "body":     pr_data.get("body", "")[:4000],  # clip to keep prompt tight
        "merged":   bool(pr_data.get("mergedAt")),
        "added":    pr_data.get("additions", 0),
        "removed":  pr_data.get("deletions", 0),
        "files":    [f.get("path", "?") for f in files],
    }

def infer_issue_from_body(body: str) -> int | None:
    m = re.search(r"(?:[Ff]ixes|[Cc]loses|[Rr]esolves)\s+#(\d+)", body or "")
    return int(m.group(1)) if m else None

# ---------------------------------------------------------------------------
# Claude summary
# ---------------------------------------------------------------------------
def render_prompt(template: str, vars_: dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        k = m.group(1)
        return str(vars_.get(k, m.group(0)))
    return re.sub(r"\{\{([A-Z_][A-Z0-9_]*)\}\}", repl, template)

def generate_summary(ticket_id: str, pr: int, issue_num: int, ctx: dict) -> dict:
    template = PROMPT_FILE.read_text()
    files = ctx["files"]
    file_preview = "\n".join(f"  - {f}" for f in files[:30])
    if len(files) > 30:
        file_preview += f"\n  … +{len(files) - 30} more"

    prompt = render_prompt(template, {
        "PR_NUM":           str(pr),
        "TICKET_ID":        ticket_id,
        "ISSUE_NUM":        str(issue_num),
        "PR_TITLE":         ctx["title"],
        "PR_BODY":          ctx["body"] or "(empty)",
        "DIFF_FILE_COUNT":  str(len(files)),
        "DIFF_FILE_LIST":   file_preview or "  (no files listed)",
        "DIFF_ADDED":       str(ctx["added"]),
        "DIFF_REMOVED":     str(ctx["removed"]),
        "GH_REPO":          GH_REPO,
    })

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(prompt)
        prompt_path = f.name

    try:
        # claude --print returns Claude's full response on stdout. We don't
        # need --dangerously-skip-permissions — this is pure text generation.
        result = subprocess.run(
            ["claude", "--print"],
            stdin=open(prompt_path),
            capture_output=True, text=True, timeout=180,
        )
    finally:
        os.unlink(prompt_path)

    if result.returncode != 0:
        die(f"claude --print failed (rc={result.returncode}): {result.stderr[:500]}")

    return parse_json_tail(result.stdout)

def parse_json_tail(text: str) -> dict:
    """Extract the trailing JSON object — Claude is prompted to emit it last."""
    # Find the last {...} block that parses as JSON.
    candidates = list(re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL))
    for m in reversed(candidates):
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if "title" in obj and "body" in obj:
            return obj
    die("could not parse JSON {title, body} from claude output")

# ---------------------------------------------------------------------------
# Canny API
# ---------------------------------------------------------------------------
def canny_create_post(title: str, body: str) -> dict:
    import urllib.parse, urllib.request

    full_title = f"{CANNY_PREFIX} {title}".strip()
    payload = urllib.parse.urlencode({
        "apiKey":   CANNY_API_KEY,
        "authorID": CANNY_ADMIN_ID,
        "boardID":  CANNY_BOARD_ID,
        "title":    full_title,
        "details":  body,
    }).encode()
    req = urllib.request.Request(
        "https://canny.io/api/v1/posts/create",
        data=payload, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        die(f"Canny posts/create failed: {e}")

    # The API returns the created post with `id` + `url`. The URL on the
    # response can be user-facing (canny.io/p/...) or an admin URL. We'll
    # attach whichever is present.
    return data

def gh_pr_comment(pr: int, body: str) -> None:
    try:
        subprocess.run(
            ["gh", "pr", "comment", str(pr), "--repo", GH_REPO, "--body", body],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except subprocess.CalledProcessError as e:
        # Non-fatal — the Canny post is already up; we just lost the linkback.
        print(f"[post-to-canny] WARN: could not comment on PR #{pr}: {e.stderr.strip()}",
              file=sys.stderr)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr",     type=int, required=True)
    ap.add_argument("--ticket", required=True)
    ap.add_argument("--issue",  type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not canny_enabled():
        log("Canny env not configured (need CANNY_API_KEY, CANNY_BOARD_ID, "
            "CANNY_ADMIN_ID) — skipping changelog post.")
        return 1

    log(f"fetching PR #{args.pr} context ...")
    ctx = fetch_pr_context(args.pr)
    if not ctx["merged"]:
        die("PR is not merged — refusing to post Canny entry")

    issue_num = args.issue or infer_issue_from_body(ctx["body"]) or 0

    log(f"generating non-technical summary (ticket={args.ticket}, issue=#{issue_num})")
    summary = generate_summary(args.ticket, args.pr, issue_num, ctx)

    log(f"summary title: {summary['title']!r}")

    if args.dry_run:
        log("--dry-run — rendered summary only, not posting")
        print(json.dumps(summary, indent=2))
        return 0

    log("creating Canny post ...")
    canny = canny_create_post(summary["title"], summary["body"])
    canny_url = canny.get("url") or canny.get("urlWithID") or ""
    canny_id  = canny.get("id", "?")
    log(f"  → Canny post id={canny_id}  url={canny_url or '(no url returned)'}")

    # Linkback comment on the GitHub PR so the dashboard can render both sides
    linkback = (
        f"Changelog posted to Canny: {canny_url}\n\n"
        f"_(Posted automatically by Phase E of ralph-rewrite-loop after squash merge. "
        f"Ticket {args.ticket}, issue #{issue_num or '?'}, Canny post id `{canny_id}`.)_"
    )
    gh_pr_comment(args.pr, linkback)
    log(f"linkback comment posted on PR #{args.pr}")

    print(f"CANNY_URL={canny_url}")
    print(f"CANNY_POST_ID={canny_id}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
