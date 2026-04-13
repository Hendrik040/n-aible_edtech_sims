#!/usr/bin/env bash
# ============================================================================
# ralph-rewrite-loop.sh — focused Ralph loop for the Claude Agent SDK rewrite
# ============================================================================
#
# Differences vs scripts/ralph-loop.sh (the generic Canny/GitHub loop):
#   - Issue source: GitHub only, filtered to label `rewrite-agent-sdk`.
#   - Ticket selection: earliest *ready* ticket (all upstream dependencies
#     merged into `rewrite/agent-sdk`) by phase/number order.
#   - Base branch: `rewrite/agent-sdk` (NOT `ralph-looped`).
#   - Merge gate: scripts/rewrite/verify-ticket.sh must exit 0 or we don't
#     merge. Non-zero → PR stays open with the gate comment, move on.
#   - Per-ticket prompt: narrow — only this ticket's scope + files +
#     verification + CodeRabbit plan. No "pick what looks good."
#   - No Canny, no Neon-branching, no Railway env cleanup. Keeps the
#     worktree-per-iteration, watchdog, and CodeRabbit review-loop patterns
#     from the original.
#
# Usage:
#   scripts/rewrite/ralph-rewrite-loop.sh                          # 5 iterations
#   scripts/rewrite/ralph-rewrite-loop.sh --iterations 10
#   scripts/rewrite/ralph-rewrite-loop.sh --iterations 0           # dry: list next-ready, exit
#   scripts/rewrite/ralph-rewrite-loop.sh --pause 60
# ============================================================================

set -uo pipefail

# --- Defaults ---------------------------------------------------------------
ITERATIONS=5
PAUSE=30
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
WORKTREE_BASE="$(cd "$REPO_DIR/.." && pwd)/work-trees"
LOG_DIR="${REPO_DIR}/scripts/rewrite/logs"
BASE_BRANCH="rewrite/agent-sdk"
LABEL="rewrite-agent-sdk"
CR_PLAN_POLL=60
CR_PLAN_MAX_POLLS=20
CLAUDE_TIMEOUT=2700
CR_REVIEW_WAIT=1200
CR_FOLLOWUP_WAIT=1200
CR_MAX_ROUNDS=4
GH_REPO="${GH_REPO_OVERRIDE:-Hendrik040/n-aible_edtech_sims}"
VERIFY_SCRIPT="${REPO_DIR}/scripts/rewrite/verify-ticket.sh"

# --- Args -------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case $1 in
    --iterations)    ITERATIONS="$2"; shift 2 ;;
    --pause)         PAUSE="$2"; shift 2 ;;
    --cr-max-rounds) CR_MAX_ROUNDS="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 64 ;;
  esac
done

mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MASTER_LOG="$LOG_DIR/rewrite_${TIMESTAMP}.log"

log() { echo "$1" | tee -a "$MASTER_LOG"; }

log "=== Ralph Rewrite Loop — $(date) ==="
log "  base branch:   $BASE_BRANCH"
log "  label filter:  $LABEL"
log "  iterations:    $ITERATIONS"
log "  pause:         ${PAUSE}s"
log "  verify script: $VERIFY_SCRIPT"
log ""

cd "$REPO_DIR"
git fetch origin "$BASE_BRANCH" 2>/dev/null || true
mkdir -p "$WORKTREE_BASE"

# ============================================================================
# Helpers
# ============================================================================

# Fetch open issues with our label, JSON: [{number, title, body}, ...].
fetch_rewrite_issues() {
  gh issue list \
    --repo "$GH_REPO" \
    --label "$LABEL" \
    --state open \
    --limit 100 \
    --json number,title,body 2>/dev/null || echo "[]"
}

# Determine which issues are *ready* (all listed "Depends on: #N" are closed
# AND their PR merged into BASE_BRANCH). Prints newline-separated
# "number|ticket_id|title" rows for ready issues, sorted by ticket id.
ready_issues() {
  local issues_json
  issues_json=$(fetch_rewrite_issues)

  python3 - "$issues_json" "$BASE_BRANCH" "$GH_REPO" <<'PY'
import json, re, subprocess, sys

issues = json.loads(sys.argv[1])
base = sys.argv[2]
repo = sys.argv[3]

TICKET_RE = re.compile(r"phase-(\d+)(?:\.(\d+))?")
DEP_RE    = re.compile(r"Depends on[\s\S]*?(?=\n###|\n##|\Z)", re.IGNORECASE)
NUM_RE    = re.compile(r"#(\d+)")

def ticket_id(title: str) -> str:
    m = TICKET_RE.search(title)
    if not m:
        return "zzz"
    return f"phase-{int(m.group(1))}.{int(m.group(2) or 0):02d}"

def deps_from_body(body: str) -> list[int]:
    if not body:
        return []
    m = DEP_RE.search(body)
    if not m:
        return []
    return [int(n) for n in NUM_RE.findall(m.group(0))]

def is_merged_into(pr_num: int, branch: str) -> bool:
    out = subprocess.run(
        ["gh", "pr", "view", str(pr_num), "--repo", repo,
         "--json", "state,mergedAt,baseRefName"],
        capture_output=True, text=True
    )
    if out.returncode != 0:
        return False
    try:
        data = json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return (data.get("state") == "MERGED"
            and data.get("baseRefName") == branch
            and bool(data.get("mergedAt")))

def dependency_met(dep_issue: int) -> bool:
    # The dep is "met" when its issue is closed AND some PR that claims
    # to fix it is merged into the base branch. We proxy this by checking
    # whether any PR in the repo targeting `base` has the issue linked via
    # closing keyword (Fixes / Closes #<n>).
    issue_res = subprocess.run(
        ["gh", "issue", "view", str(dep_issue), "--repo", repo,
         "--json", "state,closedAt"],
        capture_output=True, text=True
    )
    if issue_res.returncode != 0:
        return False
    try:
        data = json.loads(issue_res.stdout or "{}")
    except json.JSONDecodeError:
        return False
    if data.get("state") != "CLOSED":
        return False
    # Find PRs that mention the issue number and are merged into base.
    prs_res = subprocess.run(
        ["gh", "pr", "list", "--repo", repo,
         "--state", "merged", "--base", base,
         "--search", f"Fixes #{dep_issue} OR Closes #{dep_issue} OR #{dep_issue}",
         "--json", "number,baseRefName,body,title"],
        capture_output=True, text=True
    )
    if prs_res.returncode != 0:
        return False
    try:
        prs = json.loads(prs_res.stdout or "[]")
    except json.JSONDecodeError:
        return False
    for pr in prs:
        if pr.get("baseRefName") != base:
            continue
        blob = (pr.get("body", "") or "") + " " + (pr.get("title", "") or "")
        if re.search(rf"(?:[Ff]ixes|[Cc]loses|[Rr]esolves)\s+#{dep_issue}\b", blob):
            return True
    return False

rows = []
for issue in issues:
    title = issue["title"]
    tid = ticket_id(title)
    deps = deps_from_body(issue.get("body") or "")
    blocked = [d for d in deps if not dependency_met(d)]
    if blocked:
        continue
    rows.append((tid, issue["number"], title))

rows.sort()
for tid, num, title in rows:
    print(f"{num}|{tid}|{title}")
PY
}

# Extract ticket id from issue title like "[rewrite-agent-sdk] phase-1.1: foo"
ticket_id_from_title() {
  local title="$1"
  echo "$title" | grep -oE 'phase-[0-9]+(\.[0-9]+)?' | head -1
}

get_cr_plan() {
  local issue_num=$1
  gh api "repos/${GH_REPO}/issues/${issue_num}/comments" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai")) | select(.body | test("Coding Plan|## Summary|Implementation Steps"; "i"))] | last | .body // ""' \
    2>/dev/null || echo ""
}

get_cr_pr_comments() {
  local pr_num=$1
  local inline pr_comments
  inline=$(gh api "repos/${GH_REPO}/pulls/${pr_num}/comments" \
    --jq '.[] | select(.user.login | startswith("coderabbitai")) | "- " + .path + ": " + .body' 2>/dev/null || echo "")
  pr_comments=$(gh pr view "$pr_num" --repo "$GH_REPO" --json comments \
    --jq '.comments[] | select(.author.login | startswith("coderabbitai")) | .body' 2>/dev/null || echo "")
  printf '%s\n%s\n' "$inline" "$pr_comments"
}

count_cr_comments() {
  local pr_num=$1
  local ic pc
  ic=$(gh api "repos/${GH_REPO}/pulls/${pr_num}/comments" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai"))] | length' 2>/dev/null || echo "0")
  pc=$(gh pr view "$pr_num" --repo "$GH_REPO" --json comments \
    --jq '[.comments[] | select(.author.login | startswith("coderabbitai"))] | length' 2>/dev/null || echo "0")
  echo $((ic + pc))
}

cr_approved() {
  local pr_num=$1
  local n
  n=$(gh api "repos/${GH_REPO}/pulls/${pr_num}/reviews" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai")) | select(.state == "APPROVED")] | length' 2>/dev/null || echo "0")
  [ "$n" -gt 0 ]
}

ci_checks_pass() {
  local pr_num=$1
  local status
  status=$(gh pr checks "$pr_num" --repo "$GH_REPO" 2>/dev/null || echo "PENDING")
  if echo "$status" | grep -q "fail"; then return 1; fi
  return 0
}

# ---------------------------------------------------------------------------
# Watchdog — kills claude processes older than CLAUDE_TIMEOUT seconds.
# ---------------------------------------------------------------------------
start_watchdog() {
  (
    while true; do
      sleep 300
      ps -eo pid,etime,comm | awk -v max="$CLAUDE_TIMEOUT" '
        /claude/ {
          n = split($2, parts, /[-:]/)
          if (n == 2)      { secs = parts[1]*60 + parts[2] }
          else if (n == 3) { secs = parts[1]*3600 + parts[2]*60 + parts[3] }
          else if (n == 4) { secs = parts[1]*86400 + parts[2]*3600 + parts[3]*60 + parts[4] }
          else             { secs = 0 }
          if (secs > max) print $1
        }
      ' | while read -r hung_pid; do
        echo "!!! WATCHDOG: killing claude PID $hung_pid" >> "$MASTER_LOG"
        kill -TERM "$hung_pid" 2>/dev/null
        sleep 5; kill -KILL "$hung_pid" 2>/dev/null
      done
    done
  ) &
  WATCHDOG_PID=$!
}

cleanup_on_exit() {
  [ -n "${WATCHDOG_PID:-}" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
  if [ -n "${WORK_DIR:-}" ] && [ -d "${WORK_DIR:-}" ]; then
    (cd "$REPO_DIR" && git worktree remove "$WORK_DIR" --force 2>/dev/null || rm -rf "$WORK_DIR")
    (cd "$REPO_DIR" && git worktree prune 2>/dev/null || true)
  fi
}
trap cleanup_on_exit EXIT

# ============================================================================
# Dry mode: --iterations 0 → print next-ready and exit
# ============================================================================
if [ "$ITERATIONS" -eq 0 ]; then
  log "--- DRY MODE — listing ready tickets ---"
  rows=$(ready_issues)
  if [ -z "$rows" ]; then
    log "(no ready tickets — either none exist or all dependencies unmet)"
    exit 0
  fi
  log "Ready tickets (earliest first):"
  while IFS='|' read -r num tid title; do
    log "  #${num}  ${tid}  ${title}"
  done <<< "$rows"
  next=$(echo "$rows" | head -1)
  log ""
  log "Next pick: ${next}"
  exit 0
fi

start_watchdog

# ============================================================================
# MAIN LOOP
# ============================================================================
for i in $(seq 1 "$ITERATIONS"); do
  log ""
  log "============================================================"
  log "=== Iteration $i / $ITERATIONS — $(date) ==="
  log "============================================================"

  cd "$REPO_DIR"
  git fetch origin "$BASE_BRANCH" 2>/dev/null || true

  # -------------------------------------------------------------------------
  # Phase 0: pick the earliest ready ticket
  # -------------------------------------------------------------------------
  log "--- Picking ready ticket ---"
  READY_ROWS=$(ready_issues)
  if [ -z "$READY_ROWS" ]; then
    log "No ready tickets — waiting ${PAUSE}s and re-checking"
    sleep "$PAUSE"
    continue
  fi

  PICK=$(echo "$READY_ROWS" | head -1)
  ISSUE_NUM=$(echo "$PICK" | cut -d'|' -f1)
  TICKET_ID=$(echo "$PICK" | cut -d'|' -f2)
  TICKET_TITLE=$(echo "$PICK" | cut -d'|' -f3-)

  log "Picked: #${ISSUE_NUM}  ${TICKET_ID}  ${TICKET_TITLE}"

  # Skip if an open PR already exists referencing this issue.
  EXISTING_PR=$(gh pr list --repo "$GH_REPO" --base "$BASE_BRANCH" --state open \
    --search "Fixes #${ISSUE_NUM}" --json number --jq '.[0].number' 2>/dev/null || echo "")
  if [ -n "$EXISTING_PR" ] && [ "$EXISTING_PR" != "null" ]; then
    log "PR #${EXISTING_PR} already open for #${ISSUE_NUM} — skipping"
    if [ "$i" -lt "$ITERATIONS" ]; then sleep "$PAUSE"; fi
    continue
  fi

  # Create an isolated worktree off of the base branch.
  WORK_DIR="$WORKTREE_BASE/rewrite-${TICKET_ID}-$(date +%s)"
  log "Creating worktree: $WORK_DIR"
  git worktree add "$WORK_DIR" "origin/$BASE_BRANCH" --detach 2>&1 | tee -a "$MASTER_LOG"

  # -------------------------------------------------------------------------
  # Phase 1: get the CodeRabbit plan for this issue (trigger if absent)
  # -------------------------------------------------------------------------
  log "--- Fetching CodeRabbit plan for #${ISSUE_NUM} ---"
  CR_PLAN=$(get_cr_plan "$ISSUE_NUM")
  if [ -z "$CR_PLAN" ] || ! grep -qiE "coding plan|summary|implementation steps" <<< "$CR_PLAN" 2>/dev/null; then
    log "No plan yet — posting @coderabbitai plan"
    gh issue comment "$ISSUE_NUM" --repo "$GH_REPO" --body "@coderabbitai plan" >/dev/null 2>&1 || true
    for p in $(seq 1 $CR_PLAN_MAX_POLLS); do
      sleep $CR_PLAN_POLL
      CR_PLAN=$(get_cr_plan "$ISSUE_NUM")
      if [ -n "$CR_PLAN" ] && grep -qiE "coding plan|summary|implementation steps" <<< "$CR_PLAN" 2>/dev/null; then
        log "Plan received after $p polls"
        break
      fi
      log "  plan poll $p/$CR_PLAN_MAX_POLLS — still waiting..."
    done
  else
    log "Plan already exists on issue #${ISSUE_NUM}"
  fi
  if [ -z "$CR_PLAN" ]; then
    CR_PLAN="(No CodeRabbit plan available — proceed using the ticket spec as your sole guide.)"
  fi
  echo "$CR_PLAN" > "$LOG_DIR/cr_plan_${TICKET_ID}.md"

  # Pull the ticket spec block out of the breakdown so the prompt is
  # grounded in the same text CodeRabbit planned against.
  SPEC_BLOCK=$(python3 - "$REPO_DIR/plan/REWRITE_BREAKDOWN.md" "$TICKET_ID" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
want = sys.argv[2]
parts = re.split(r"^(### phase-[0-9.]+:.*)$", text, flags=re.M)
# parts alternates: [prelude, header1, body1, header2, body2, ...]
for i in range(1, len(parts), 2):
    header = parts[i]
    body = parts[i+1] if i+1 < len(parts) else ""
    if header.startswith(f"### {want}:"):
        print(header + body.split("### phase-", 1)[0])
        break
PY
)

  # -------------------------------------------------------------------------
  # Phase 2: implement the ticket
  # -------------------------------------------------------------------------
  log "--- Implementing ticket ${TICKET_ID} ---"
  IMPL_LOG="$LOG_DIR/impl_${TICKET_ID}_iter${i}.log"

  cd "$WORK_DIR"
  claude --print --dangerously-skip-permissions "\
You are implementing a single ticket in the n-aible EdTech rewrite.
Working directory: ${WORK_DIR} (git worktree off origin/${BASE_BRANCH}).

READ CLAUDE.md first for project context.

## TICKET — exact spec from plan/REWRITE_BREAKDOWN.md
${SPEC_BLOCK}

## CODERABBIT PLAN
${CR_PLAN}

## STRICT RULES

1. STAY IN SCOPE. The 'files' line above lists every path you are allowed to
   create or modify. Anything outside that list will be rejected by the
   verifier (exit 1, scope mismatch).
2. WRITE THE TESTS NAMED IN 'unit_tests_required'. Each function must exist
   by that exact name in the matching test file — the verifier greps for
   'def <name>' literally.
3. For every .py source file you create under backend_v2/, create a matching
   test file at backend_v2/tests/<same-rel-path>/test_<name>.py (enforced
   by the verifier).
4. All new unit tests must pass AND cover the touched source files at ≥85%
   (enforced via pytest --cov-fail-under=85).
5. If 'contract_tests_required' is not 'none', implement every listed case
   name in backend_v2/tests/contract/<module>/test_*.py and confirm they
   pass against backend_v2.
6. DO NOT touch infrastructure files (.env, docker-compose.yml, CI workflows)
   unless this ticket's scope explicitly includes them.
7. DO NOT add dependencies unless the scope calls for them.

## WORKFLOW

1. Create a branch:
     git checkout -b ${TICKET_ID}-impl
2. Implement the scope + the required tests.
3. Run the verifier locally BEFORE pushing:
     bash ${VERIFY_SCRIPT} ${TICKET_ID}
   It must exit 0. If not, fix the problems it reports and re-run.
4. Commit with a message that starts with the ticket id:
     ${TICKET_ID}: <short summary>

     Fixes #${ISSUE_NUM}

     <details>
5. Push: git push -u origin ${TICKET_ID}-impl
6. Open the PR against ${BASE_BRANCH}:
     gh pr create --repo ${GH_REPO} --base ${BASE_BRANCH} \\
       --label ${LABEL} --label ${TICKET_ID%%.*} \\
       --title '${TICKET_ID}: <summary>' \\
       --body 'Fixes #${ISSUE_NUM}\\n\\nImplements ticket ${TICKET_ID}. See the issue for the full spec.'
7. Print at the end: PR_NUMBER=<number>

If you cannot complete the ticket, print SKIP_ITERATION and exit without
pushing." 2>&1 | tee "$IMPL_LOG"

  PR_NUM=$(grep -oE 'PR_NUMBER=[0-9]+' "$IMPL_LOG" | tail -1 | cut -d= -f2 || echo "")
  if [ -z "$PR_NUM" ]; then
    PR_NUM=$(grep -oE 'pull/[0-9]+' "$IMPL_LOG" | tail -1 | grep -oE '[0-9]+' || echo "")
  fi

  if [ -z "$PR_NUM" ]; then
    log "!!! No PR produced — skipping rest of iteration"
    cd "$REPO_DIR"
    git worktree remove "$WORK_DIR" --force 2>/dev/null || rm -rf "$WORK_DIR"
    git worktree prune 2>/dev/null || true
    if [ "$i" -lt "$ITERATIONS" ]; then sleep "$PAUSE"; fi
    continue
  fi

  log "PR #${PR_NUM} opened for ticket ${TICKET_ID}"

  # -------------------------------------------------------------------------
  # Phase 3: CodeRabbit review loop (verbatim pattern from the generic loop)
  # -------------------------------------------------------------------------
  log "--- CodeRabbit review loop ---"
  REVIEW_ROUND=0
  PREV_COUNT=$(count_cr_comments "$PR_NUM")

  # wait for first review
  CR_REVIEW_POLLS_MAX=$((CR_REVIEW_WAIT / 60))
  for p in $(seq 1 $CR_REVIEW_POLLS_MAX); do
    sleep 60
    if [ -n "$(get_cr_pr_comments "$PR_NUM")" ]; then break; fi
    log "  first-review poll $p/$CR_REVIEW_POLLS_MAX"
  done

  while [ "$REVIEW_ROUND" -lt "$CR_MAX_ROUNDS" ]; do
    REVIEW_ROUND=$((REVIEW_ROUND + 1))
    log "--- Review round $REVIEW_ROUND / $CR_MAX_ROUNDS ---"

    if cr_approved "$PR_NUM"; then
      log "CodeRabbit APPROVED #${PR_NUM}"
      break
    fi

    CR_FEEDBACK=$(get_cr_pr_comments "$PR_NUM")
    CURRENT_COUNT=$(count_cr_comments "$PR_NUM")
    if [ "$REVIEW_ROUND" -gt 1 ] && [ "$CURRENT_COUNT" -eq "$PREV_COUNT" ]; then
      log "No new CR comments — feedback resolved"
      break
    fi

    HAS_ACTIONABLE=$(echo "$CR_FEEDBACK" | python3 -c "
import sys
text = sys.stdin.read().lower()
if any(s in text for s in ['suggestion','issue','bug','error','warning','consider','should','must','missing','incorrect','fix']):
    if 'no issues found' in text or 'lgtm' in text:
        print('no')
    else:
        print('yes')
else:
    print('no')
")
    if [ "$HAS_ACTIONABLE" = "no" ] || [ -z "$CR_FEEDBACK" ]; then
      log "No actionable CR feedback — moving on"
      break
    fi

    log "Addressing CR feedback..."
    REVIEW_LOG="$LOG_DIR/review_${TICKET_ID}_iter${i}_r${REVIEW_ROUND}.log"
    (cd "$WORK_DIR" && claude --print --dangerously-skip-permissions "\
You are on branch ${TICKET_ID}-impl with open PR #${PR_NUM} against ${BASE_BRANCH}.
CodeRabbit left the following review feedback:

${CR_FEEDBACK}

Rules:
- Address every actionable point; skip false positives but explain briefly.
- Keep all changes within the files listed in the ticket's scope (see the
  issue body — the verifier will still enforce this).
- After your edits, run: bash ${VERIFY_SCRIPT} ${TICKET_ID} — it must exit 0.
- Commit with: '${TICKET_ID}: address CodeRabbit review round ${REVIEW_ROUND}'
- Push." 2>&1 | tee "$REVIEW_LOG" | tail -15)

    PREV_COUNT=$CURRENT_COUNT

    # wait for re-review
    FOLLOWUP_POLLS=$((CR_FOLLOWUP_WAIT / 60))
    for p in $(seq 1 $FOLLOWUP_POLLS); do
      sleep 60
      if cr_approved "$PR_NUM"; then
        log "  CR APPROVED after round ${REVIEW_ROUND}"
        break 2
      fi
      NEW=$(count_cr_comments "$PR_NUM")
      if [ "$NEW" -ne "$PREV_COUNT" ]; then
        log "  new feedback detected (${PREV_COUNT} → ${NEW})"
        break
      fi
      log "  re-review poll $p/$FOLLOWUP_POLLS"
    done
  done

  # -------------------------------------------------------------------------
  # Phase 4: verification gate — the thing the old loop was missing
  # -------------------------------------------------------------------------
  log "--- Running verify-ticket.sh (merge gate) ---"
  (cd "$WORK_DIR" && bash "$VERIFY_SCRIPT" "$TICKET_ID" "$PR_NUM") 2>&1 | tee "$LOG_DIR/verify_${TICKET_ID}_iter${i}.log"
  VERIFY_EXIT=${PIPESTATUS[0]}

  if [ "$VERIFY_EXIT" -ne 0 ]; then
    log "!!! verify-ticket.sh exit ${VERIFY_EXIT} — PR #${PR_NUM} NOT merged"
    gh pr comment "$PR_NUM" --repo "$GH_REPO" --body "Verification gate failed (exit ${VERIFY_EXIT}). See verify-ticket.sh output. PR left open for manual intervention." >/dev/null 2>&1 || true
    cd "$REPO_DIR"
    git worktree remove "$WORK_DIR" --force 2>/dev/null || rm -rf "$WORK_DIR"
    git worktree prune 2>/dev/null || true
    if [ "$i" -lt "$ITERATIONS" ]; then sleep "$PAUSE"; fi
    continue
  fi

  # -------------------------------------------------------------------------
  # Phase 5: CI gate + squash merge
  # -------------------------------------------------------------------------
  log "--- CI gate ---"
  sleep 60
  CI_OK=false
  for attempt in 1 2 3; do
    if ci_checks_pass "$PR_NUM"; then CI_OK=true; break; fi
    log "CI not green yet (attempt $attempt/3) — sleeping 60s"
    sleep 60
  done

  if [ "$CI_OK" = true ]; then
    log "CI green — squash-merging PR #${PR_NUM}"
    gh pr merge "$PR_NUM" --repo "$GH_REPO" --squash --delete-branch 2>&1 | tee -a "$MASTER_LOG"
    gh issue close "$ISSUE_NUM" --repo "$GH_REPO" --comment "Resolved by PR #${PR_NUM} (verify-ticket.sh passed)." >/dev/null 2>&1 || true
    log "PR #${PR_NUM} merged. Ticket ${TICKET_ID} done."
  else
    log "!!! CI red — leaving PR #${PR_NUM} open for manual review"
  fi

  cd "$REPO_DIR"
  git worktree remove "$WORK_DIR" --force 2>/dev/null || rm -rf "$WORK_DIR"
  git worktree prune 2>/dev/null || true

  log "--- Iteration $i complete ---"
  if [ "$i" -lt "$ITERATIONS" ]; then sleep "$PAUSE"; fi
done

log ""
log "============================================================"
log "=== Rewrite loop COMPLETE — $(date) ==="
log "============================================================"
log "Open PRs on ${BASE_BRANCH} needing review:"
gh pr list --repo "$GH_REPO" --base "$BASE_BRANCH" --state open 2>/dev/null | tee -a "$MASTER_LOG"
log "Full log: $MASTER_LOG"
