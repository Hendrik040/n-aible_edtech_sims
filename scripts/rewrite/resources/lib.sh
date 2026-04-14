#!/usr/bin/env bash
# ralph-rewrite-loop — shared shell helpers. Sourced by the main loop
# after config.sh. Every function here is side-effect-safe to redefine.
# shellcheck disable=SC2034,SC2155

# ===========================================================================
# Logging
# ===========================================================================
log() {
  local ts; ts=$(date +'%H:%M:%S')
  if [ -n "${MASTER_LOG:-}" ]; then
    printf '[%s] %s\n' "$ts" "$*" | tee -a "$MASTER_LOG"
  else
    printf '[%s] %s\n' "$ts" "$*"
  fi
}
die() { log "ERROR: $*"; exit 1; }

# ===========================================================================
# Pipeline telemetry — fire-and-forget POST to admin dashboard (PR-B)
# ===========================================================================
# emit_event <phase> <status> [detail] [duration_sec] [context_json]
# Never blocks the loop (posts in a detached subshell, always returns 0).
# Silent no-op if RALPH_EVENT_URL or RALPH_EVENT_TOKEN unset — lets dev
# runs not require telemetry config.
emit_event() {
  [ -n "${RALPH_EVENT_URL:-}" ] || return 0
  [ -n "${RALPH_EVENT_TOKEN:-}" ] || return 0
  local phase=$1 status=$2 detail=${3:-} duration=${4:-} ctx=${5:-}
  local payload
  payload=$(
    TICKET_ID="${TICKET_ID:-}" ITER="${ITER:-0}" \
    LOOP_RUN_ID="${LOOP_RUN_ID:-${TIMESTAMP:-unknown}}" \
    PR_NUM="${PR_NUM:-}" ISSUE_NUM="${ISSUE_NUM:-}" \
    _P="$phase" _S="$status" _D="$detail" _DU="$duration" _C="$ctx" \
    python3 - <<'PY'
import json, os
def _int(v):
    try: return int(v) if v else None
    except ValueError: return None
body = {
    "ticket_id":   os.environ.get("TICKET_ID", "") or "phase-0.0",
    "iteration":   max(1, _int(os.environ.get("ITER")) or 1),
    "loop_run_id": os.environ.get("LOOP_RUN_ID") or "unknown",
    "pr_number":   _int(os.environ.get("PR_NUM")),
    "issue_number": _int(os.environ.get("ISSUE_NUM")),
    "phase":       os.environ["_P"],
    "status":      os.environ["_S"],
    "detail":      os.environ.get("_D") or None,
    "duration_sec": _int(os.environ.get("_DU")),
    "context":     json.loads(os.environ["_C"]) if os.environ.get("_C") else None,
}
print(json.dumps(body))
PY
  )
  (
    curl -sfL -X POST "${RALPH_EVENT_URL%/}/api/admin/ralph-pipeline/event" \
      -H "Authorization: Bearer ${RALPH_EVENT_TOKEN}" \
      -H "Content-Type: application/json" \
      --max-time 5 \
      -d "$payload" >/dev/null 2>&1 || true
  ) &
  disown 2>/dev/null || true
  return 0
}

# ===========================================================================
# GitHub API helpers (all read against $GH_REPO)
# ===========================================================================
gh_issue_list_open() {
  gh issue list \
    --repo "$GH_REPO" --label "$LABEL" \
    --state open --limit 100 \
    --json number,title,body 2>/dev/null || echo "[]"
}

# Ready tickets = upstream deps all merged into $BASE_BRANCH. Emits
# "issue_num|ticket_id|title" rows sorted by ticket id, earliest first.
pick_ready_tickets() {
  local issues_json
  issues_json=$(gh_issue_list_open)
  python3 - "$issues_json" "$BASE_BRANCH" "$GH_REPO" "$LABEL" <<'PY'
import json, re, subprocess, sys
issues = json.loads(sys.argv[1])
base   = sys.argv[2]
repo   = sys.argv[3]
label  = sys.argv[4]

TICKET_RE = re.compile(r"phase-(\d+)(?:\.(\d+))?")
DEP_RE    = re.compile(r"###\s*Depends on\s*\n(.*?)(?=\n###|\Z)", re.IGNORECASE | re.DOTALL)
NUM_RE    = re.compile(r"#(\d+)")

def ticket_id(title):
    m = TICKET_RE.search(title)
    return f"phase-{int(m.group(1))}.{int(m.group(2) or 0):02d}" if m else "zzz"

def deps(body):
    if not body:
        return []
    m = DEP_RE.search(body)
    return [int(n) for n in NUM_RE.findall(m.group(1))] if m else []

def _pr_strictly_closes(n, state):
    """Return True iff a PR (in `state`) on `base`, labeled `label`,
    strictly closes issue #n via Fixes/Closes/Resolves."""
    p = subprocess.run(
        ["gh", "pr", "list", "--repo", repo,
         "--state", state, "--base", base,
         "--label", label,
         "--search", f"Fixes #{n} OR Closes #{n} OR Resolves #{n}",
         "--json", "number,body,title"],
        capture_output=True, text=True
    )
    if p.returncode != 0:
        return False
    try:
        prs = json.loads(p.stdout)
    except json.JSONDecodeError:
        return False
    for pr in prs:
        blob = (pr.get("body","") or "") + " " + (pr.get("title","") or "")
        if re.search(rf"(?:[Ff]ixes|[Cc]loses|[Rr]esolves)\s+#{n}\b", blob):
            return True
    return False

def _merged_pr_for(n):
    """Return True iff a merged PR on `base`, labeled `label`, strictly
    closes issue #n. Scoping to `label` avoids false-positives from
    unrelated tooling PRs that happen to mention the ticket number."""
    return _pr_strictly_closes(n, "merged")

def _open_pr_for(n):
    """Return True iff an open PR on `base`, labeled `label`, strictly
    closes issue #n. Used to exclude tickets that already have work in
    flight — otherwise the picker keeps returning them and the loop
    wastes iterations logging "PR already open — skipping"."""
    return _pr_strictly_closes(n, "open")

def dep_met(n):
    # A dependency is satisfied once its closing PR is merged into
    # base. We do NOT require the issue itself to be CLOSED because
    # `Fixes #N` only auto-closes on default-branch merges, not on
    # merges into `ralph-looped` — so a merged-but-still-OPEN issue
    # must count as met, otherwise downstream tickets stall.
    return _merged_pr_for(n)

rows = []
for i in issues:
    # Skip tickets whose PR is already merged. Issues on `ralph-looped`
    # don't auto-close on merge (Fixes # only fires for the default
    # branch), so a merged-but-still-OPEN issue would otherwise be
    # re-picked forever.
    if _merged_pr_for(i["number"]):
        continue
    # Skip tickets that already have an open PR. These are in-flight
    # work — a new iteration shouldn't try to re-implement them; the
    # pre-iteration sweep (sweep_ready_prs) will pick them up once
    # they're APPROVED + CI-green.
    if _open_pr_for(i["number"]):
        continue
    blocked = [d for d in deps(i.get("body","") or "") if not dep_met(d)]
    if not blocked:
        rows.append((ticket_id(i["title"]), i["number"], i["title"]))
rows.sort()
for tid, n, t in rows:
    print(f"{n}|{tid}|{t}")
PY
}

pr_already_open_for() {
  # Scope: only PRs labeled `rewrite-agent-sdk` (excludes tooling PRs that
  # happen to mention a ticket number in their body). Match: strict regex
  # on closing keywords, not loose full-text search — gh's --search matches
  # any occurrence of "430", so unrelated PR bodies can false-positive.
  local issue=$1
  gh pr list --repo "$GH_REPO" --base "$BASE_BRANCH" --state open \
    --label "$LABEL" --limit 50 --json number,body \
    --jq ".[] | select(.body | test(\"(?i)(?:fixes|closes|resolves)\\\\s+#${issue}\\\\b\")) | .number" \
    2>/dev/null | head -1
}

# ===========================================================================
# PR sweep — merge any APPROVED + CLEAN + CI-green PRs that are just sitting.
# ===========================================================================
# Called at the top of every iteration (and in --iterations 0 dry mode as a
# preview). Fixes the "stranded PR" failure mode where Phase A opened a PR
# but C/D errored or the loop got killed, leaving the PR approved + green
# with nobody to merge it.
#
# Flags:
#   dry_run=1  -> print "would merge" lines instead of actually merging.
sweep_ready_prs() {
  local dry_run=${1:-0}
  local prs_json
  prs_json=$(gh pr list --repo "$GH_REPO" --base "$BASE_BRANCH" \
    --state open --label "$LABEL" --limit 50 \
    --json number,body,title,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup \
    2>/dev/null || echo "[]")

  # Filter to mergeable PRs in a single python pass. Output one line per
  # ready PR: "pr_num|issue_num_or_empty|ticket_id_or_unknown".
  local ready
  ready=$(python3 - "$prs_json" <<'PY'
import json, re, sys
prs = json.loads(sys.argv[1])

TICKET_RE = re.compile(r"phase-(\d+)(?:\.(\d+))?")
CLOSES_RE = re.compile(r"(?:[Ff]ixes|[Cc]loses|[Rr]esolves)\s+#(\d+)\b")

def all_checks_green(rollup):
    if not rollup:
        # No required checks configured → treat as green.
        return True
    for c in rollup:
        state = (c.get("state") or c.get("conclusion") or "").upper()
        if state != "SUCCESS":
            return False
    return True

def issue_num_from_body(body):
    if not body:
        return None
    m = CLOSES_RE.search(body)
    return int(m.group(1)) if m else None

for pr in prs:
    if (pr.get("mergeable") or "").upper() != "MERGEABLE":          continue
    if (pr.get("mergeStateStatus") or "").upper() != "CLEAN":        continue
    if (pr.get("reviewDecision") or "").upper() != "APPROVED":       continue
    if not all_checks_green(pr.get("statusCheckRollup") or []):      continue
    num   = pr.get("number")
    issue = issue_num_from_body(pr.get("body",""))
    issue_s = str(issue) if issue else ""
    print(f"{num}|{issue_s}|")
PY
)

  if [ -z "$ready" ]; then
    log "  sweep: 0 PRs ready to merge"
    return 0
  fi

  # For each ready PR, resolve ticket_id from the linked issue's title
  # (same TICKET_RE as the picker). Then merge (or preview) and emit
  # telemetry. ticket_id resolution failure does NOT block the merge.
  while IFS='|' read -r pr_num issue_num _; do
    [ -z "$pr_num" ] && continue
    local ticket_id="unknown"
    local detail=""
    if [ -n "$issue_num" ]; then
      local issue_title
      issue_title=$(gh issue view "$issue_num" --repo "$GH_REPO" \
        --json title --jq .title 2>/dev/null || echo "")
      if [ -n "$issue_title" ]; then
        ticket_id=$(python3 - "$issue_title" <<'PY'
import re, sys
m = re.search(r"phase-(\d+)(?:\.(\d+))?", sys.argv[1])
print(f"phase-{int(m.group(1))}.{int(m.group(2) or 0):02d}" if m else "unknown")
PY
        )
      fi
    fi
    if [ "$ticket_id" = "unknown" ]; then
      detail="ticket_id unresolved"
    fi

    if [ "$dry_run" = "1" ]; then
      log "  sweep: would sweep-merge PR #${pr_num} (ticket=${ticket_id}, all checks green)"
      continue
    fi

    log "  sweep: merging PR #${pr_num} (ticket=${ticket_id}, all checks green)"
    if gh pr merge "$pr_num" --repo "$GH_REPO" --squash --delete-branch >/dev/null 2>&1; then
      PR_NUM="$pr_num" ISSUE_NUM="${issue_num:-}" TICKET_ID="$ticket_id" \
        emit_event "D-merge" "passed" "${detail:-swept by sweep_ready_prs}"
    else
      log "  sweep: merge FAILED for PR #${pr_num} — leaving for manual attention"
      PR_NUM="$pr_num" ISSUE_NUM="${issue_num:-}" TICKET_ID="$ticket_id" \
        emit_event "D-merge" "failed" "sweep_ready_prs merge failed"
    fi
  done <<< "$ready"
}

get_cr_plan() {
  local issue=$1
  gh api "repos/${GH_REPO}/issues/${issue}/comments" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai"))
           | select(.body | test("Coding Plan|## Summary|Implementation Steps"; "i"))]
          | last | .body // ""' 2>/dev/null
}

get_cr_pr_comments() {
  local pr=$1
  local inline; inline=$(gh api "repos/${GH_REPO}/pulls/${pr}/comments" \
    --jq '.[] | select(.user.login | startswith("coderabbitai")) | "- " + .path + ": " + .body' 2>/dev/null)
  local summary; summary=$(gh pr view "$pr" --repo "$GH_REPO" --json comments \
    --jq '.comments[] | select(.author.login | startswith("coderabbitai")) | .body' 2>/dev/null)
  printf '%s\n%s\n' "$inline" "$summary"
}

count_cr_pr_comments() {
  local pr=$1
  local ic; ic=$(gh api "repos/${GH_REPO}/pulls/${pr}/comments" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai"))] | length' 2>/dev/null || echo 0)
  local pc; pc=$(gh pr view "$pr" --repo "$GH_REPO" --json comments \
    --jq '[.comments[] | select(.author.login | startswith("coderabbitai"))] | length' 2>/dev/null || echo 0)
  echo $((ic + pc))
}

cr_approved() {
  local pr=$1
  local n; n=$(gh api "repos/${GH_REPO}/pulls/${pr}/reviews" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai")) | select(.state == "APPROVED")] | length' 2>/dev/null || echo 0)
  [ "$n" -gt 0 ]
}

ci_checks_pass() {
  local pr=$1
  local status; status=$(gh pr checks "$pr" --repo "$GH_REPO" 2>/dev/null || echo "PENDING")
  ! echo "$status" | grep -q "fail"
}

# ===========================================================================
# Worktree management
# ===========================================================================
refresh_anchor() {
  # Fast-forward the anchor onto origin/$BASE_BRANCH so every new worktree
  # starts from the latest integration-trunk state. Ff-only — never
  # clobbers anchor commits.
  git -C "$REPO_DIR" fetch --quiet origin "$BASE_BRANCH" "$ANCHOR_BRANCH" 2>/dev/null || true
  if git -C "$REPO_DIR" merge-base --is-ancestor \
        "origin/${ANCHOR_BRANCH}" "origin/${BASE_BRANCH}" 2>/dev/null; then
    log "anchor '${ANCHOR_BRANCH}' is behind '${BASE_BRANCH}' — fast-forwarding"
    git -C "$REPO_DIR" push --quiet origin \
      "origin/${BASE_BRANCH}:${ANCHOR_BRANCH}" 2>/dev/null \
      || log "  (ff-push failed — anchor may already be up to date)"
  fi
}

worktree_create() {
  # Create an isolated worktree off origin/$ANCHOR_BRANCH. Prints the
  # path on stdout.
  local ticket_id=$1
  local dir="${WORKTREE_BASE}/rewrite-${ticket_id}-$(date +%s)"
  git -C "$REPO_DIR" worktree add "$dir" "origin/$ANCHOR_BRANCH" --detach >/dev/null 2>&1 \
    || { log "worktree create failed for $ticket_id"; return 1; }
  echo "$dir"
}

worktree_cleanup() {
  local dir=$1
  [ -z "$dir" ] && return 0
  git -C "$REPO_DIR" worktree remove "$dir" --force >/dev/null 2>&1 \
    || rm -rf "$dir" 2>/dev/null
  git -C "$REPO_DIR" worktree prune >/dev/null 2>&1 || true
}

# ===========================================================================
# Slug generation (keep in sync with scripts/rewrite/migrate-to-ralph-looped.py)
# ===========================================================================
ticket_slug() {
  # Args: title
  python3 - "$1" <<'PY'
import re, sys
t = sys.argv[1].lower()
t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
skip = {"the","a","an","py","into","for","with","and","or","of"}
parts = [p for p in t.split("-") if p not in skip]
print(("-".join(parts)[:40]).strip("-"))
PY
}

feature_branch_for() {
  # Args: ticket_id, ticket_title
  echo "${FEATURE_PREFIX}/${1}-$(ticket_slug "$2")"
}

# ===========================================================================
# Prompt rendering (replaces {{VAR}} tokens from env, no shell interpolation)
# ===========================================================================
render_prompt() {
  # Args: prompt_template_path -> stdout is the rendered prompt.
  # Only replaces {{UPPERCASE_VAR}} tokens whose corresponding env var
  # is exported; leaves all other double-braced text untouched. Safe for
  # prompts that contain code examples with curly braces.
  python3 - "$1" <<'PY'
import os, re, sys
text = open(sys.argv[1]).read()
def repl(m):
    k = m.group(1)
    return os.environ.get(k, m.group(0))
print(re.sub(r"\{\{([A-Z_][A-Z0-9_]*)\}\}", repl, text))
PY
}

# ===========================================================================
# Claude invocation
# ===========================================================================
run_claude_in() {
  # Args: cwd, prompt_text_file, log_file
  local cwd=$1 prompt=$2 log=$3
  (cd "$cwd" && claude --print --dangerously-skip-permissions < "$prompt") \
    2>&1 | tee "$log"
}

# ===========================================================================
# Watchdog — kills the loop's own claude subprocesses if they hang past
# CLAUDE_TIMEOUT_SEC. Must NOT match the user's interactive Claude Code
# sessions (which also have "claude" in their cmdline) — we key on the
# exact argv run_claude_in invokes: `claude --print --dangerously-skip-permissions`.
# ===========================================================================
start_watchdog() {
  (
    while true; do
      sleep 300
      # BSD awk (macOS) rejects chained ternaries — use if/else.
      ps -eo pid,etime,command | awk -v max="$CLAUDE_TIMEOUT_SEC" '
        /claude --print --dangerously-skip-permissions/ {
          n = split($2, p, /[-:]/)
          if (n == 2)      { s = p[1]*60 + p[2] }
          else if (n == 3) { s = p[1]*3600 + p[2]*60 + p[3] }
          else if (n == 4) { s = p[1]*86400 + p[2]*3600 + p[3]*60 + p[4] }
          else             { s = 0 }
          if (s > max) print $1
        }
      ' | while read -r pid; do
        echo "WATCHDOG: killing hung claude PID $pid" >> "${MASTER_LOG:-/dev/stderr}"
        kill -TERM "$pid" 2>/dev/null; sleep 5; kill -KILL "$pid" 2>/dev/null
      done
    done
  ) &
  WATCHDOG_PID=$!
}

stop_watchdog() {
  [ -n "${WATCHDOG_PID:-}" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
}
