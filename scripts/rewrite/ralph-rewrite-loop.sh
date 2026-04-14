#!/usr/bin/env bash
# ============================================================================
# ralph-rewrite-loop.sh — thin orchestrator for the rewrite-agent-sdk track.
#
# Reads tickets from GitHub (label `rewrite-agent-sdk`), picks the earliest
# "ready" one (all upstream PRs merged into `ralph-looped`), and lands one
# PR per iteration. Every per-step rule + prompt lives in resources/; this
# file is only the control flow so it stays readable end-to-end.
#
# Usage:
#   scripts/rewrite/ralph-rewrite-loop.sh                        # default: 5 iters
#   scripts/rewrite/ralph-rewrite-loop.sh --iterations 10
#   scripts/rewrite/ralph-rewrite-loop.sh --iterations 0         # dry: print next-ready
#   scripts/rewrite/ralph-rewrite-loop.sh --ticket phase-0.1     # run one specific ticket
#
# For the full per-iteration flowchart, see scripts/rewrite/WORKFLOW.md.
# ============================================================================

set -uo pipefail

# --- Source config + helpers (resources/ owns all the details) --------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=resources/config.sh
. "$SCRIPT_DIR/resources/config.sh"
# shellcheck source=resources/lib.sh
. "$SCRIPT_DIR/resources/lib.sh"

# --- Parse args -------------------------------------------------------------
ONLY_TICKET=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --iterations) ITERATIONS="$2"; shift 2 ;;
    --pause)      PAUSE_BETWEEN="$2"; shift 2 ;;
    --ticket)     ONLY_TICKET="$2"; shift 2 ;;
    --cr-rounds)  CR_MAX_ROUNDS="$2"; shift 2 ;;
    -h|--help)    sed -n '4,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)            die "unknown arg: $1 (try --help)" ;;
  esac
done

# --- Log setup --------------------------------------------------------------
mkdir -p "$LOG_DIR" "$WORKTREE_BASE"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MASTER_LOG="${LOG_DIR}/rewrite_${TIMESTAMP}.log"

log "════════════════════════════════════════════════════════════════"
log "Ralph Rewrite Loop  ·  $(date)"
log "  base:        $BASE_BRANCH"
log "  anchor:      $ANCHOR_BRANCH"
log "  label:       $LABEL"
log "  iterations:  $ITERATIONS (pause=${PAUSE_BETWEEN}s between)"
log "  CR rounds:   up to $CR_MAX_ROUNDS per PR"
log "  workdir:     $WORKTREE_BASE"
log "  log:         $MASTER_LOG"
log "════════════════════════════════════════════════════════════════"

# --- Dry mode ---------------------------------------------------------------
if [ "$ITERATIONS" -eq 0 ]; then
  log ""
  log "DRY MODE — ready tickets (earliest first):"
  rows=$(pick_ready_tickets)
  if [ -z "$rows" ]; then
    log "  (none — either no open tickets, or all have unmet deps)"
  else
    while IFS='|' read -r num tid title; do
      log "  #${num}  ${tid}  ${title}"
    done <<< "$rows"
  fi
  exit 0
fi

# ============================================================================
# Per-iteration phases
# ============================================================================

# Phase A: Claude implements the ticket and opens a PR. Returns PR number
# on stdout (empty if skipped/failed).
phase_implement() {
  local work_dir=$1 issue_num=$2 ticket_id=$3 ticket_title=$4 spec=$5 plan=$6
  local prompt_file="${LOG_DIR}/prompt_${ticket_id}_impl.md"
  local run_log="${LOG_DIR}/impl_${ticket_id}_iter${ITER}.log"

  # Render the implement prompt with env-var tokens.
  export TICKET_ID="$ticket_id" \
         ISSUE_NUM="$issue_num" \
         TICKET_SPEC="$spec" \
         CR_PLAN="$plan" \
         FEATURE_BRANCH="$(feature_branch_for "$ticket_id" "$ticket_title")" \
         BASE_BRANCH ANCHOR_BRANCH LABEL GH_REPO
  render_prompt "${PROMPTS_DIR}/implement.md" > "$prompt_file"

  log "  → invoking Claude for implementation (log: $(basename "$run_log"))"
  run_claude_in "$work_dir" "$prompt_file" "$run_log" >/dev/null

  # Extract PR number; Claude is prompted to print PR_NUMBER=<n>.
  grep -oE 'PR_NUMBER=[0-9]+' "$run_log" | tail -1 | cut -d= -f2
}

# Phase B: run CR-review loop on the open PR. Returns 0 when there's no
# outstanding actionable feedback (approved / no new comments); 1 if we
# hit the round cap still dirty.
phase_address_feedback() {
  local work_dir=$1 issue_num=$2 ticket_id=$3 ticket_title=$4 pr_num=$5
  local feature_branch; feature_branch=$(feature_branch_for "$ticket_id" "$ticket_title")

  # Wait for the first CR-bot comment to appear.
  local polls=$((CR_REVIEW_WAIT_SEC / 60)) i
  log "  waiting for first CodeRabbit PR review (polling every 60s, up to ${polls} times / ${CR_REVIEW_WAIT_SEC}s)"
  for i in $(seq 1 "$polls"); do
    sleep 60
    if [ -n "$(get_cr_pr_comments "$pr_num")" ]; then log "  CR review arrived (poll ${i}/${polls})"; break; fi
    log "  CR PR-review poll ${i}/${polls} — no review yet"
  done

  local round=0 prev_count
  prev_count=$(count_cr_pr_comments "$pr_num")

  while [ "$round" -lt "$CR_MAX_ROUNDS" ]; do
    round=$((round + 1))

    # Fast path: CR approved.
    if cr_approved "$pr_num"; then
      log "  CR approved PR #${pr_num} (round ${round})"
      return 0
    fi

    # If no new comments since our last push, feedback was resolved.
    local now_count; now_count=$(count_cr_pr_comments "$pr_num")
    if [ "$round" -gt 1 ] && [ "$now_count" -eq "$prev_count" ]; then
      log "  no new CR comments after push — treating as resolved"
      return 0
    fi

    log "  round ${round}/${CR_MAX_ROUNDS} — addressing CR feedback"

    local prompt_file="${LOG_DIR}/prompt_${ticket_id}_round${round}.md"
    local run_log="${LOG_DIR}/review_${ticket_id}_iter${ITER}_r${round}.log"
    export TICKET_ID="$ticket_id" ISSUE_NUM="$issue_num" PR_NUM="$pr_num" \
           FEATURE_BRANCH="$feature_branch" BASE_BRANCH GH_REPO \
           ROUND="$round" MAX_ROUNDS="$CR_MAX_ROUNDS"
    render_prompt "${PROMPTS_DIR}/address-pr-feedback.md" > "$prompt_file"
    run_claude_in "$work_dir" "$prompt_file" "$run_log" >/dev/null

    prev_count="$now_count"

    # Give CR time to re-review after the push.
    local wait_polls=$((CR_FOLLOWUP_WAIT_SEC / 60)) j
    log "  waiting for CR re-review after round ${round} (polling every 60s, up to ${wait_polls} times)"
    for j in $(seq 1 "$wait_polls"); do
      sleep 60
      cr_approved "$pr_num" && { log "  CR approved after round ${round} (poll ${j}/${wait_polls})"; return 0; }
      local n; n=$(count_cr_pr_comments "$pr_num")
      if [ "$n" -ne "$prev_count" ]; then log "  new CR feedback detected (poll ${j}/${wait_polls})"; break; fi
      log "  CR re-review poll ${j}/${wait_polls} — no new feedback yet"
    done
  done

  log "  hit CR_MAX_ROUNDS=${CR_MAX_ROUNDS} without clean state"
  return 1
}

# Phase C: run testing skills. Returns 0 if Claude prints ALL_TESTS_PASSED.
phase_run_tests() {
  local work_dir=$1 issue_num=$2 ticket_id=$3 ticket_title=$4 pr_num=$5
  local prompt_file="${LOG_DIR}/prompt_${ticket_id}_tests.md"
  local run_log="${LOG_DIR}/tests_${ticket_id}_iter${ITER}.log"
  local feature_branch; feature_branch=$(feature_branch_for "$ticket_id" "$ticket_title")

  export TICKET_ID="$ticket_id" ISSUE_NUM="$issue_num" PR_NUM="$pr_num" \
         FEATURE_BRANCH="$feature_branch" BASE_BRANCH GH_REPO
  render_prompt "${PROMPTS_DIR}/run-tests.md" > "$prompt_file"

  log "  → invoking Claude for testing (log: $(basename "$run_log"))"
  run_claude_in "$work_dir" "$prompt_file" "$run_log" >/dev/null

  if grep -q '^ALL_TESTS_PASSED' "$run_log"; then
    log "  ✅ ALL_TESTS_PASSED"
    return 0
  fi
  local reason; reason=$(grep -oE '^TESTS_FAILED:.*' "$run_log" | head -1)
  log "  ❌ ${reason:-tests did not report pass}"
  return 1
}

# Phase D: wait for CI + squash merge.
phase_merge() {
  local pr_num=$1
  log "  polling CI (every ${CI_POLL_SEC}s, up to ${CI_MAX_POLLS} times)"
  local i
  for i in $(seq 1 "$CI_MAX_POLLS"); do
    if ci_checks_pass "$pr_num"; then
      log "  CI green — merging PR #${pr_num}"
      gh pr merge "$pr_num" --repo "$GH_REPO" --squash --delete-branch 2>&1 | tee -a "$MASTER_LOG"
      return 0
    fi
    log "  CI poll ${i}/${CI_MAX_POLLS} — not green yet"
    sleep "$CI_POLL_SEC"
  done
  log "  CI not green after polls — leaving PR #${pr_num} open"
  return 1
}

# Phase E: post a Canny changelog entry for the merged PR. Non-fatal on
# any failure — a missed changelog never blocks the next iteration.
# Only invoked after phase_merge returned 0 (successful squash merge).
phase_post_canny() {
  local pr_num=$1 ticket_id=$2 issue_num=$3
  local run_log="${LOG_DIR}/canny_${ticket_id}_iter${ITER}.log"

  if [ -z "$CANNY_API_KEY" ] || [ -z "$CANNY_BOARD_ID" ] || [ -z "$CANNY_ADMIN_ID" ]; then
    log "  Canny env vars not set — skipping changelog post"
    return 0
  fi

  log "  → posting Canny changelog for PR #${pr_num}"
  export CANNY_API_KEY CANNY_BOARD_ID CANNY_ADMIN_ID CANNY_TITLE_PREFIX GH_REPO
  if python3 "${RESOURCES_DIR}/post-to-canny.py" \
       --pr "$pr_num" --ticket "$ticket_id" --issue "$issue_num" \
       > "$run_log" 2>&1; then
    local url; url=$(grep -oE 'CANNY_URL=.+' "$run_log" | tail -1 | cut -d= -f2-)
    log "  Canny post ok${url:+ — $url}"
  else
    log "  WARN: Canny post failed (see $(basename "$run_log")) — not blocking loop"
  fi
}

# ============================================================================
# Main loop
# ============================================================================
cleanup_on_exit() {
  stop_watchdog
  worktree_cleanup "${WORK_DIR:-}"
}
trap cleanup_on_exit EXIT

start_watchdog
refresh_anchor

for ITER in $(seq 1 "$ITERATIONS"); do
  log ""
  log "─── iteration ${ITER}/${ITERATIONS} ─────────────────────────────"

  # --- Pick next ticket (or the one the user pinned) -----------------------
  if [ -n "$ONLY_TICKET" ]; then
    row=$(pick_ready_tickets | grep -F "|${ONLY_TICKET}|" | head -1)
  else
    row=$(pick_ready_tickets | head -1)
  fi
  [ -z "$row" ] && { log "no ready tickets — pausing ${PAUSE_BETWEEN}s"; sleep "$PAUSE_BETWEEN"; continue; }

  ISSUE_NUM=$(echo "$row" | cut -d'|' -f1)
  TICKET_ID=$(echo "$row" | cut -d'|' -f2)
  TICKET_TITLE=$(echo "$row" | cut -d'|' -f3-)
  log "picked: #${ISSUE_NUM}  ${TICKET_ID}  ${TICKET_TITLE}"

  # Skip if a PR is already open for this issue.
  existing=$(pr_already_open_for "$ISSUE_NUM")
  if [ -n "$existing" ] && [ "$existing" != "null" ]; then
    log "  PR #${existing} already open — skipping"
    sleep "$PAUSE_BETWEEN"; continue
  fi

  # --- Create worktree -----------------------------------------------------
  WORK_DIR=$(worktree_create "$TICKET_ID") || { sleep "$PAUSE_BETWEEN"; continue; }
  log "  worktree: ${WORK_DIR}"

  # --- Fetch ticket spec + CodeRabbit plan ---------------------------------
  TICKET_SPEC=$(gh issue view "$ISSUE_NUM" --repo "$GH_REPO" --json body --jq .body)
  CR_PLAN=$(get_cr_plan "$ISSUE_NUM")
  if [ -z "$CR_PLAN" ]; then
    log "  no CodeRabbit plan yet — triggering and polling (every ${CR_PLAN_POLL_SEC}s, up to ${CR_PLAN_MAX_POLLS} times)"
    gh issue comment "$ISSUE_NUM" --repo "$GH_REPO" --body "@coderabbitai plan" >/dev/null 2>&1 || true
    for p in $(seq 1 "$CR_PLAN_MAX_POLLS"); do
      sleep "$CR_PLAN_POLL_SEC"
      CR_PLAN=$(get_cr_plan "$ISSUE_NUM")
      if [ -n "$CR_PLAN" ]; then log "  plan received (poll ${p}/${CR_PLAN_MAX_POLLS})"; break; fi
      log "  CR plan poll ${p}/${CR_PLAN_MAX_POLLS} — still waiting"
    done
  else
    log "  CodeRabbit plan already present on issue — skipping poll"
  fi
  [ -z "$CR_PLAN" ] && CR_PLAN="(no CodeRabbit plan; proceed using the ticket spec as sole guide)"

  # --- Phase A: implement --------------------------------------------------
  PR_NUM=$(phase_implement "$WORK_DIR" "$ISSUE_NUM" "$TICKET_ID" "$TICKET_TITLE" "$TICKET_SPEC" "$CR_PLAN")
  if [ -z "$PR_NUM" ]; then
    log "  no PR produced — ending iteration"
    worktree_cleanup "$WORK_DIR"; WORK_DIR=""; sleep "$PAUSE_BETWEEN"; continue
  fi
  log "  PR opened: #${PR_NUM}"

  # --- Phase B: CR review loop --------------------------------------------
  phase_address_feedback "$WORK_DIR" "$ISSUE_NUM" "$TICKET_ID" "$TICKET_TITLE" "$PR_NUM" \
    || log "  CR review loop hit round cap (proceeding anyway — tests will catch issues)"

  # --- Phase C: testing skills ---------------------------------------------
  if ! phase_run_tests "$WORK_DIR" "$ISSUE_NUM" "$TICKET_ID" "$TICKET_TITLE" "$PR_NUM"; then
    log "  tests failed — leaving PR #${PR_NUM} open for manual review"
    gh pr comment "$PR_NUM" --repo "$GH_REPO" \
      --body "Ralph loop: testing phase failed (see logs). PR left open for manual review." >/dev/null 2>&1 || true
    worktree_cleanup "$WORK_DIR"; WORK_DIR=""; sleep "$PAUSE_BETWEEN"; continue
  fi

  # --- Phase D: CI gate + merge -------------------------------------------
  if phase_merge "$PR_NUM"; then
    # --- Phase E: Canny changelog (merge-only, non-fatal on failure) ------
    phase_post_canny "$PR_NUM" "$TICKET_ID" "$ISSUE_NUM"
  else
    log "  PR #${PR_NUM} left open (CI red) — skipping Canny changelog"
  fi

  worktree_cleanup "$WORK_DIR"; WORK_DIR=""
  log "─── iteration ${ITER} done ─────────────────────────────────────"
  [ "$ITER" -lt "$ITERATIONS" ] && sleep "$PAUSE_BETWEEN"
done

log ""
log "════════════════════════════════════════════════════════════════"
log "Loop complete.  Open PRs on ${BASE_BRANCH}:"
gh pr list --repo "$GH_REPO" --base "$BASE_BRANCH" --state open 2>/dev/null | tee -a "$MASTER_LOG"
log "════════════════════════════════════════════════════════════════"
