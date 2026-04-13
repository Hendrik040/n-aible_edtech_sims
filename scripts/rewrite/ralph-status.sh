#!/usr/bin/env bash
# ============================================================================
# ralph-status.sh — at-a-glance dashboard for a running (or recent) Ralph
#                   rewrite loop.
#
# Pulls answers to the four questions you actually care about when checking
# in on the loop:
#   1. is the loop even alive?
#   2. which ticket is it on and what phase?
#   3. is Claude actively doing something, or silently polling?
#   4. is there an open PR, and what's CodeRabbit/CI/Railway saying?
#
# Usage:
#   scripts/rewrite/ralph-status.sh             # one-shot snapshot
#   scripts/rewrite/ralph-status.sh --watch     # refresh every 10s (Ctrl-C to stop)
#   scripts/rewrite/ralph-status.sh --log       # also tail the last 30 log lines
#   scripts/rewrite/ralph-status.sh --help
# ============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=resources/config.sh
. "$SCRIPT_DIR/resources/config.sh"

WATCH=0; SHOW_LOG=0
while [[ $# -gt 0 ]]; do
  case $1 in
    --watch|-w) WATCH=1; shift ;;
    --log|-l)   SHOW_LOG=1; shift ;;
    --help|-h)  sed -n '4,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)          echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

hr() { printf '%s\n' "────────────────────────────────────────────────────────────"; }

# --- Human-friendly elapsed since a unix timestamp -------------------------
since() {
  local then=$1 now
  now=$(date +%s)
  local d=$((now - then))
  if   [ "$d" -lt 60 ];    then printf "%ds"       "$d"
  elif [ "$d" -lt 3600 ];  then printf "%dm%02ds"  $((d/60)) $((d%60))
  elif [ "$d" -lt 86400 ]; then printf "%dh%02dm"  $((d/3600)) $(((d%3600)/60))
  else                         printf "%dd%02dh"   $((d/86400)) $(((d%86400)/3600))
  fi
}

snapshot() {
  clear 2>/dev/null
  echo "Ralph loop status  ·  $(date '+%Y-%m-%d %H:%M:%S')"
  hr

  # 1. Loop process state --------------------------------------------------
  local main_pid
  main_pid=$(pgrep -f 'bash scripts/rewrite/ralph-rewrite-loop.sh' 2>/dev/null | head -1)
  if [ -n "$main_pid" ]; then
    local started_at
    started_at=$(ps -o lstart= -p "$main_pid" 2>/dev/null | sed 's/^ *//;s/ *$//')
    # BSD ps has no `etimes` — parse `etime` (DD-HH:MM:SS | HH:MM:SS | MM:SS).
    local uptime_s
    uptime_s=$(ps -o etime= -p "$main_pid" 2>/dev/null | awk '
      { n = split($1, p, /[-:]/)
        if (n == 2)      { s = p[1]*60 + p[2] }
        else if (n == 3) { s = p[1]*3600 + p[2]*60 + p[3] }
        else if (n == 4) { s = p[1]*86400 + p[2]*3600 + p[3]*60 + p[4] }
        else             { s = 0 }
        print s
      }')
    local subshells
    subshells=$(pgrep -f 'bash scripts/rewrite/ralph-rewrite-loop.sh' 2>/dev/null | wc -l | tr -d ' ')
    echo "  loop       ✅ alive   PID=${main_pid}  (+${subshells} subshells)"
    [ -n "$uptime_s" ] && [ "$uptime_s" -gt 0 ] 2>/dev/null \
        && echo "             uptime     $(since $(($(date +%s) - uptime_s)))"
    [ -n "$started_at" ] && echo "             started    ${started_at}"
  else
    echo "  loop       ❌ not running"
  fi

  # 2. Master log — most recent entry + phase detection -------------------
  local latest_log
  latest_log=$(ls -t "${LOG_DIR}"/rewrite_*.log 2>/dev/null | head -1)
  if [ -n "$latest_log" ]; then
    local last_line; last_line=$(tail -1 "$latest_log" 2>/dev/null)
    local last_mtime; last_mtime=$(stat -f '%m' "$latest_log" 2>/dev/null)
    local phase="unknown"
    # Walk the log bottom-up to find the most recent phase marker.
    if grep -q '→ invoking Claude for testing'            "$latest_log"; then phase="C-testing"; fi
    if grep -q '→ invoking Claude for implementation'     "$latest_log" \
       && ! grep -q '→ invoking Claude for testing'       "$latest_log"; then phase="A-implement"; fi
    if grep -q 'waiting for first CodeRabbit PR review'   "$latest_log" \
       && ! grep -q '→ invoking Claude for testing'       "$latest_log"; then phase="B-review"; fi
    if grep -q 'polling CI'                               "$latest_log" \
       && ! grep -q 'CI green — merging'                  "$latest_log"; then phase="D-ci"; fi
    if grep -q 'CI green — merging'                       "$latest_log" \
       && ! grep -q 'Canny post ok\|Canny post failed'    "$latest_log"; then phase="E-canny"; fi
    echo "  log file   ${latest_log/${REPO_DIR}\//}"
    [ -n "$last_mtime" ] && echo "             last write $(since "$last_mtime") ago"
    echo "             phase      ${phase}"
    echo "             last line  ${last_line}"
  else
    echo "  log file   (none yet)"
  fi

  # 3. Claude subprocess ---------------------------------------------------
  local claude_line
  claude_line=$(ps -eo pid,etime,args | awk '/ claude --print/ && !/awk/ {print; exit}')
  if [ -n "$claude_line" ]; then
    echo "  claude     ✅ running"
    echo "             $(echo "$claude_line" | awk '{printf "PID=%s  runtime=%s", $1, $2}')"
    # Most recent bash subprocess Claude spawned (the actual work).
    local worker
    worker=$(ps -eo pid,etime,comm,args \
             | grep -E 'uv sync|pytest|alembic|pip install' \
             | grep -v 'grep ' | head -1)
    [ -n "$worker" ] && echo "             worker     $(echo "$worker" | awk '{printf "%s (runtime %s)", $3, $2}')"
  else
    echo "  claude     ∅ not running (either between phases or loop finished)"
  fi

  # 4. Current worktree ----------------------------------------------------
  local wt
  wt=$(ls -dt "${WORKTREE_BASE}"/rewrite-* 2>/dev/null | head -1)
  if [ -n "$wt" ]; then
    local wt_size; wt_size=$(du -sh "$wt" 2>/dev/null | awk '{print $1}')
    local wt_branch; wt_branch=$(git -C "$wt" branch --show-current 2>/dev/null)
    echo "  worktree   ${wt/${WORKTREE_BASE}\//}"
    echo "             size     ${wt_size:-?}"
    echo "             branch   ${wt_branch:-<detached>}"
    # Show any staged/unstaged work inside the worktree.
    local wt_changes
    wt_changes=$(git -C "$wt" status --short 2>/dev/null | wc -l | tr -d ' ')
    echo "             changes  ${wt_changes} file(s) dirty"
  fi

  # 5. Open PR (if any) ---------------------------------------------------
  local pr_json
  pr_json=$(gh pr list --repo "$GH_REPO" --base "$BASE_BRANCH" --state open \
              --label "$LABEL" --limit 5 --json number,title,mergeable,reviewDecision,statusCheckRollup 2>/dev/null)
  if [ -n "$pr_json" ] && [ "$pr_json" != "[]" ]; then
    echo ""
    echo "  open rewrite-agent-sdk PRs on ${BASE_BRANCH}:"
    echo "$pr_json" | python3 - <<'PY'
import json, sys
prs = json.load(sys.stdin)
for pr in prs:
    checks = pr.get("statusCheckRollup") or []
    n_fail = sum(1 for c in checks if c.get("conclusion") == "FAILURE")
    n_pass = sum(1 for c in checks if c.get("conclusion") == "SUCCESS")
    n_pend = sum(1 for c in checks if c.get("conclusion") in (None, "PENDING"))
    review = pr.get("reviewDecision") or "—"
    mergeable = pr.get("mergeable") or "?"
    print(f"    #{pr['number']}  {pr['title'][:60]}")
    print(f"         review={review}  mergeable={mergeable}  CI=✅{n_pass}/❌{n_fail}/⏳{n_pend}")
PY
  fi

  # 6. Tail recent log lines if asked -------------------------------------
  if [ "$SHOW_LOG" = "1" ] && [ -n "$latest_log" ]; then
    echo ""
    echo "  recent log (last 30 lines):"
    tail -30 "$latest_log" | sed 's/^/    /'
  fi

  hr
}

if [ "$WATCH" = "1" ]; then
  while true; do snapshot; sleep 10; done
else
  snapshot
fi
