#!/bin/bash
# ============================================================================
# Ralph Loop — Issue-driven continuous improvement for n-aible
# ============================================================================
# Full workflow per iteration:
#
#   PHASE 0: Fetch issues from Canny (by votes) + GitHub Issues
#   PHASE 1: Claude picks highest-impact issue, creates GitHub issue for it
#            → triggers @coderabbitai plan → waits for CodeRabbit's plan
#   PHASE 2: Claude implements the fix using CodeRabbit's plan as guide,
#            writes unit/integration tests, creates feature branch + PR
#   PHASE 3: Wait for CodeRabbit PR review, Claude addresses feedback
#   PHASE 4: CI gate — merge only when checks pass
#
# Usage:
#   ./scripts/ralph-loop.sh                        # 10 iterations
#   ./scripts/ralph-loop.sh --iterations 5
#   ./scripts/ralph-loop.sh --pause 60
#   ./scripts/ralph-loop.sh --include-completed
# ============================================================================

set -euo pipefail

# --- Defaults ----------------------------------------------------------------
ITERATIONS=10
PAUSE=30
SKIP_COMPLETED=true
CANNY_API_KEY=""
CANNY_BOARD_ID=""
BASE_BRANCH="ralph-looped"
LOG_DIR="scripts/ralph-logs"
CR_PLAN_POLL=60        # poll every 60s for plan
CR_PLAN_MAX_POLLS=20   # max polls (20 min total — CR plans can take 15-20 min)
CR_REVIEW_WAIT=900     # 15 minutes for first CodeRabbit PR review
CR_FOLLOWUP_WAIT=600   # 10 minutes for follow-up reviews
CR_MAX_ROUNDS=4        # max review-fix cycles per PR
GH_REPO="Hendrik040/n-aible_edtech_sims"

# --- Load .env ---------------------------------------------------------------
ENV_FILE="$(git rev-parse --show-toplevel 2>/dev/null)/.env"
if [ -f "$ENV_FILE" ]; then
  CANNY_API_KEY=$(grep '^CANNY_API_KEY=' "$ENV_FILE" | cut -d= -f2-)
  CANNY_BOARD_ID=$(grep '^CANNY_BOARD_ID=' "$ENV_FILE" | cut -d= -f2-)
  CANNY_ADMIN_ID=$(grep '^CANNY_ADMIN_ID=' "$ENV_FILE" | cut -d= -f2-)
fi

if [ -z "$CANNY_API_KEY" ]; then
  echo "ERROR: CANNY_API_KEY not found. Set it in .env at the repo root."
  exit 1
fi

if [ -z "$CANNY_ADMIN_ID" ]; then
  echo "WARNING: CANNY_ADMIN_ID not found in .env — Canny status updates will be skipped."
fi

# --- Parse args --------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case $1 in
    --iterations)        ITERATIONS="$2";       shift 2 ;;
    --pause)             PAUSE="$2";            shift 2 ;;
    --skip-completed)    SKIP_COMPLETED=true;   shift ;;
    --include-completed) SKIP_COMPLETED=false;  shift ;;
    --cr-max-rounds)     CR_MAX_ROUNDS="$2";    shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# --- Setup -------------------------------------------------------------------
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MASTER_LOG="$LOG_DIR/ralph_${TIMESTAMP}.log"
BLOCKED_FILE="$LOG_DIR/blocked_tickets.json"

# Initialize blocked tickets file if it doesn't exist
if [ ! -f "$BLOCKED_FILE" ]; then
  echo '[]' > "$BLOCKED_FILE"
fi

log() {
  echo "$1" | tee -a "$MASTER_LOG"
}

log "=== Ralph Loop starting at $(date) ==="
log "  Base branch: $BASE_BRANCH"
log "  Iterations: $ITERATIONS"
log "  Pause: ${PAUSE}s"
log "  CodeRabbit plan: poll ${CR_PLAN_POLL}s x ${CR_PLAN_MAX_POLLS} max, review wait: ${CR_REVIEW_WAIT}s"
log ""

# Ensure we're on the right branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$BASE_BRANCH" ]; then
  log "Switching to branch $BASE_BRANCH..."
  git checkout "$BASE_BRANCH"
fi

git pull origin "$BASE_BRANCH" 2>/dev/null || true

# --- Fetch issues function ---------------------------------------------------
fetch_issues() {
  CANNY_POSTS=$(curl -s -X POST https://canny.io/api/v1/posts/list \
    -d "apiKey=${CANNY_API_KEY}" \
    -d "boardID=${CANNY_BOARD_ID}" \
    -d "sort=score" \
    -d "limit=30")

  local tmp_canny=$(mktemp)
  local tmp_gh=$(mktemp)
  trap "rm -f $tmp_canny $tmp_gh" RETURN

  echo "$CANNY_POSTS" | python3 -c "
import json, sys
data = json.load(sys.stdin)
skip_completed = sys.argv[1] == 'true'
skip_statuses = {'complete', 'closed'} if skip_completed else {'closed'}
issues = []
for p in data.get('posts', []):
    if p.get('status','') in skip_statuses:
        continue
    cat = p.get('category', {})
    cat_name = cat.get('name', 'Uncategorized') if cat else 'Uncategorized'
    details = (p.get('details', '') or '')[:300].replace('\n', ' ')
    is_bug = 'bug' in cat_name.lower()
    issues.append({
        'source': 'canny',
        'id': p['id'],
        'title': p['title'],
        'score': p.get('score', 0),
        'status': p.get('status', 'open'),
        'category': cat_name,
        'is_bug': is_bug,
        'details': details,
        'url': p.get('url', '')
    })
print(json.dumps(issues))
" "$SKIP_COMPLETED" > "$tmp_canny"

  gh issue list --limit 20 --state open --json number,title,body,labels 2>/dev/null \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
issues = []
for i in data:
    body = (i.get('body', '') or '')[:300].replace('\n', ' ')
    labels = ', '.join([l.get('name','') for l in i.get('labels', [])])
    is_bug = 'bug' in labels.lower()
    issues.append({
        'source': 'github',
        'id': str(i['number']),
        'title': i['title'],
        'score': 0,
        'status': 'open',
        'category': labels or 'github-issue',
        'is_bug': is_bug,
        'details': body,
        'url': ''
    })
print(json.dumps(issues))
" > "$tmp_gh"

  python3 -c "
import json, sys
canny = json.load(open(sys.argv[1]))
github = json.load(open(sys.argv[2]))
all_issues = canny + github
print(json.dumps(all_issues, indent=2))
" "$tmp_canny" "$tmp_gh"
}

# --- Get CodeRabbit plan from issue comments ---------------------------------
get_cr_plan() {
  local issue_num=$1
  gh api "repos/${GH_REPO}/issues/${issue_num}/comments" \
    --jq '.[] | select(.user.login | startswith("coderabbitai")) | .body' 2>/dev/null || echo ""
}

# --- Get CodeRabbit comments on a PR ----------------------------------------
get_cr_pr_comments() {
  local pr_num=$1
  INLINE=$(gh api "repos/${GH_REPO}/pulls/${pr_num}/comments" \
    --jq '.[] | select(.user.login | startswith("coderabbitai")) | "- " + .path + ": " + .body' 2>/dev/null || echo "")
  PR_COMMENTS=$(gh pr view "$pr_num" --json comments \
    --jq '.comments[] | select(.author.login | startswith("coderabbitai")) | .body' 2>/dev/null || echo "")
  echo "${INLINE}"
  echo "${PR_COMMENTS}"
}

# --- Update Canny post status and add comment --------------------------------
update_canny_post() {
  local post_id=$1
  local status=$2  # "in progress", "complete", etc.
  local comment=$3

  if [ -z "$CANNY_ADMIN_ID" ]; then
    log "  (Skipping Canny update — no CANNY_ADMIN_ID)"
    return
  fi

  # Change status
  curl -s -X POST https://canny.io/api/v1/posts/change_status \
    -d "apiKey=${CANNY_API_KEY}" \
    -d "postID=${post_id}" \
    -d "changerID=${CANNY_ADMIN_ID}" \
    -d "status=${status}" \
    -d "shouldNotifyVoters=false" \
    -d "commentValue=${comment}" > /dev/null 2>&1

  log "  Canny post ${post_id} → status: ${status}"
}

# --- Notify user (macOS notification + terminal bell) ------------------------
notify_user() {
  local title=$1
  local message=$2
  # macOS notification
  osascript -e "display notification \"${message}\" with title \"Ralph Loop\" subtitle \"${title}\"" 2>/dev/null || true
  # Terminal bell
  printf '\a'
  log "NOTIFICATION: ${title} — ${message}"
}

# --- Block a ticket: create GH issue, notify user, park it ------------------
block_ticket() {
  local original_issue=$1
  local canny_post_id=$2
  local what_is_needed=$3  # description of what the agent needs

  # Create a "blocked" GitHub issue asking for help
  BLOCKED_ISSUE_URL=$(gh issue create \
    --title "ralph-blocked: need input for #${original_issue}" \
    --label "ralph-blocked" \
    --body "$(cat <<EOF
## Ralph Loop needs your help

While working on issue #${original_issue}, the agent determined it needs additional information or tools to proceed.

### What is needed
${what_is_needed}

### How to unblock
1. Reply to this issue with the requested information (API keys, credentials, tool setup instructions, etc.)
2. Ralph Loop will automatically pick this up on its next pass and resume work

### Context
- **Original issue:** #${original_issue}
$([ -n "$canny_post_id" ] && echo "- **Canny post:** ${canny_post_id}")
- **Blocked at:** $(date)
- **Ralph Loop iteration:** will retry automatically

---
*Reply to this issue to unblock. Ralph Loop checks for replies each iteration.*
EOF
)" 2>&1)

  BLOCKED_ISSUE_NUM=$(echo "$BLOCKED_ISSUE_URL" | grep -oE '[0-9]+$' || echo "")

  # Add to blocked tickets file
  python3 -c "
import json
blocked = json.load(open('${BLOCKED_FILE}'))
blocked.append({
    'original_issue': '${original_issue}',
    'blocked_issue': '${BLOCKED_ISSUE_NUM}',
    'canny_post_id': '${canny_post_id}',
    'what_needed': '''${what_is_needed}'''[:500],
    'blocked_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
})
json.dump(blocked, open('${BLOCKED_FILE}', 'w'), indent=2)
"

  # Notify the user immediately
  notify_user "Blocked on #${original_issue}" "Need: ${what_is_needed:0:100}"

  log "Blocked ticket created: #${BLOCKED_ISSUE_NUM} (needs input for #${original_issue})"

  # Update Canny if applicable
  if [ -n "$canny_post_id" ]; then
    update_canny_post "$canny_post_id" "under review" \
      "Ralph Loop needs additional information to fix this. See: https://github.com/${GH_REPO}/issues/${BLOCKED_ISSUE_NUM}"
  fi
}

# --- Check blocked tickets for user replies ----------------------------------
check_blocked_tickets() {
  local unblocked_issues=""

  BLOCKED_COUNT=$(python3 -c "import json; print(len(json.load(open('${BLOCKED_FILE}'))))")

  if [ "$BLOCKED_COUNT" = "0" ]; then
    return
  fi

  log "--- Checking ${BLOCKED_COUNT} blocked ticket(s) for user replies ---"

  # Check each blocked ticket for new comments (user replies)
  unblocked_issues=$(python3 -c "
import json, subprocess, sys

blocked = json.load(open('${BLOCKED_FILE}'))
still_blocked = []
unblocked = []

for ticket in blocked:
    issue_num = ticket['blocked_issue']
    if not issue_num:
        continue

    # Check for non-bot comments on the blocked issue
    result = subprocess.run(
        ['gh', 'api', 'repos/${GH_REPO}/issues/' + issue_num + '/comments',
         '--jq', '[.[] | select(.user.login != \"github-actions[bot]\" and .user.login != \"coderabbitai[bot]\")] | length'],
        capture_output=True, text=True
    )
    comment_count = int(result.stdout.strip() or '0')

    if comment_count > 0:
        unblocked.append(ticket)
    else:
        still_blocked.append(ticket)

json.dump(still_blocked, open('${BLOCKED_FILE}', 'w'), indent=2)

for t in unblocked:
    print(f\"{t['blocked_issue']}|{t['original_issue']}|{t['canny_post_id']}\")
")

  if [ -n "$unblocked_issues" ]; then
    while IFS='|' read -r blocked_num orig_num canny_id; do
      log "Ticket #${orig_num} UNBLOCKED (user replied on #${blocked_num})"

      # Get the user's reply
      USER_REPLY=$(gh api "repos/${GH_REPO}/issues/${blocked_num}/comments" \
        --jq '[.[] | select(.user.login != "github-actions[bot]" and .user.login != "coderabbitai")] | last | .body' 2>/dev/null || echo "")

      if [ -n "$USER_REPLY" ]; then
        log "User provided: ${USER_REPLY:0:200}..."

        # Add the user's reply as context to the original issue
        gh issue comment "$orig_num" --body "$(cat <<EOF
## Additional context from user (unblocked)

The following information was provided in response to #${blocked_num}:

${USER_REPLY}

---
*Ralph Loop will now retry this issue with the above context.*
EOF
)" 2>/dev/null || true

        # Close the blocked issue
        gh issue close "$blocked_num" --comment "Unblocked! User provided the requested information. Resuming work on #${orig_num}." 2>/dev/null || true
      fi

      notify_user "Unblocked #${orig_num}" "User replied — will retry this iteration"
    done <<< "$unblocked_issues"
  fi
}

# --- Check if CI checks pass ------------------------------------------------
ci_checks_pass() {
  local pr_num=$1
  STATUS=$(gh pr checks "$pr_num" 2>/dev/null || echo "PENDING")
  if echo "$STATUS" | grep -q "fail"; then
    return 1
  fi
  return 0
}

# =============================================================================
# MAIN LOOP
# =============================================================================
for i in $(seq 1 "$ITERATIONS"); do
  ITER_LOG="$LOG_DIR/ralph_${TIMESTAMP}_iter${i}.log"

  log ""
  log "============================================================"
  log "=== ITERATION $i / $ITERATIONS — $(date) ==="
  log "============================================================"

  # Always start from base branch
  git checkout "$BASE_BRANCH"
  git pull origin "$BASE_BRANCH" 2>/dev/null || true

  # ===========================================================================
  # PHASE 0: Check blocked tickets + fetch issues
  # ===========================================================================
  check_blocked_tickets

  log "--- Phase 0: Fetching issues ---"

  ISSUES_JSON=$(fetch_issues 2>/dev/null)
  echo "$ISSUES_JSON" > "$LOG_DIR/issues_iter${i}.json"

  ISSUE_SUMMARY=$(echo "$ISSUES_JSON" | python3 -c "
import json, sys
issues = json.load(sys.stdin)
lines = []
for idx, i in enumerate(issues):
    src = i['source'].upper()
    bug_tag = ' [BUG]' if i.get('is_bug') else ''
    canny_id = f\" canny_post_id={i['id']}\" if i['source'] == 'canny' else ''
    lines.append(f\"  [{src}] score={i['score']} status={i['status']}{bug_tag}{canny_id} | {i['title']}\")
    if i['details']:
        lines.append(f\"         {i['details'][:150]}\")
print('\n'.join(lines[:60]))
")

  log "Issues found:"
  log "$ISSUE_SUMMARY"
  log ""

  # ===========================================================================
  # PHASE 1: Pick issue → create GitHub issue → get CodeRabbit plan
  # ===========================================================================
  log "--- Phase 1: Pick issue & get CodeRabbit plan ---"

  # Use Claude to pick the issue and create a GitHub issue
  PICK_LOG="$LOG_DIR/ralph_${TIMESTAMP}_iter${i}_pick.log"

  claude --print --dangerously-skip-permissions \
    "You are working on the n-aible EdTech simulation platform.

## YOUR TASK — Pick ONE issue and create a GitHub issue for it

Below is a prioritized list of issues from Canny (user feedback, sorted by votes) and GitHub Issues.
Pick the SINGLE HIGHEST-IMPACT issue you can fix with code changes, starting from the top (most upvoted).
Skip issues that need infra changes (API keys, Docker, env vars, external services like Daytona).

## ISSUE LIST (priority order — bugs tagged [BUG]):
${ISSUE_SUMMARY}

## INSTRUCTIONS:
1. Pick the best issue (prefer [BUG] over feature requests)
2. If the issue already exists as a GitHub issue, use that issue number instead of creating a new one
3. If it does NOT exist as a GitHub issue, create one:
   gh issue create --title '<clear title>' --body '<detailed description including:
   - What the bug/issue is
   - Steps to reproduce (if applicable)
   - Expected vs actual behavior
   - Source: Canny (score: X) or GitHub
   - Any relevant file paths or error messages>'
4. After creating (or identifying) the issue, trigger CodeRabbit plan:
   gh issue comment <issue_number> --body '@coderabbitai plan'
5. Print the issue number at the end: ISSUE_NUMBER=<number>
6. If the issue came from Canny, also print: CANNY_POST_ID=<the canny_post_id from the issue list>

## BLOCKING — when you need something you don't have
If the issue requires tools, API keys, credentials, or external setup that you
cannot do yourself, DO NOT just skip it. Instead:
1. Still create the GitHub issue (or use existing one)
2. Print: BLOCKED=yes
3. Print: BLOCKED_REASON=<clear description of what you need, e.g. 'Need SMTP credentials for password reset emails' or 'Need Stripe API key for billing integration'>
4. Print: ISSUE_NUMBER=<number>
5. Print: CANNY_POST_ID=<id> (if from Canny)
The loop will create a help-request issue, notify the user, and move to the next ticket.
The blocked ticket will be automatically retried when the user replies.

## RULES:
- Do NOT fix anything yet — only create the issue and trigger the plan
- Do NOT create duplicate issues — check existing open issues first
- Be thorough in the issue description so CodeRabbit has good context
- If the issue is from Canny, include 'Source: Canny (score: X, post_id: Y)' in the GitHub issue body
- Use BLOCKED when you need external input — don't silently skip good issues" \
    2>&1 | tee "$PICK_LOG"

  # Extract issue number
  ISSUE_NUM=$(grep -oE 'ISSUE_NUMBER=[0-9]+' "$PICK_LOG" | tail -1 | cut -d= -f2 || echo "")

  if [ -z "$ISSUE_NUM" ]; then
    ISSUE_NUM=$(grep -oE '#[0-9]+' "$PICK_LOG" | tail -1 | tr -d '#' || echo "")
  fi

  if [ -z "$ISSUE_NUM" ]; then
    log "!!! Could not determine issue number — skipping iteration"
    if [ "$i" -lt "$ITERATIONS" ]; then sleep "$PAUSE"; fi
    continue
  fi

  # Extract Canny post ID if present
  CANNY_POST_ID=$(grep -oE 'CANNY_POST_ID=[a-f0-9]+' "$PICK_LOG" | tail -1 | cut -d= -f2 || echo "")

  # Check if the agent flagged this as blocked
  IS_BLOCKED=$(grep -oE 'BLOCKED=yes' "$PICK_LOG" | tail -1 || echo "")
  if [ -n "$IS_BLOCKED" ]; then
    BLOCKED_REASON=$(grep -oE 'BLOCKED_REASON=.*' "$PICK_LOG" | tail -1 | sed 's/BLOCKED_REASON=//' || echo "Unknown — agent needs input")
    log "BLOCKED: Issue #${ISSUE_NUM} needs user input: ${BLOCKED_REASON}"
    block_ticket "$ISSUE_NUM" "$CANNY_POST_ID" "$BLOCKED_REASON"
    log "--- Moving to next ticket ---"
    if [ "$i" -lt "$ITERATIONS" ]; then sleep "$PAUSE"; fi
    continue
  fi

  log "GitHub Issue #${ISSUE_NUM} created/selected"
  if [ -n "$CANNY_POST_ID" ]; then
    log "Canny Post ID: ${CANNY_POST_ID}"
    # Mark as "in progress" on Canny
    update_canny_post "$CANNY_POST_ID" "in progress" "Ralph Loop is working on this. GitHub Issue: https://github.com/${GH_REPO}/issues/${ISSUE_NUM}"
  fi

  log "Waiting for CodeRabbit plan..."

  # Poll for CodeRabbit plan
  CR_PLAN=""
  POLL_COUNT=0
  log "Waiting for CodeRabbit to generate plan (polling every ${CR_PLAN_POLL}s, max ${CR_PLAN_MAX_POLLS} polls)..."

  while [ "$POLL_COUNT" -lt "$CR_PLAN_MAX_POLLS" ]; do
    POLL_COUNT=$((POLL_COUNT + 1))
    sleep "$CR_PLAN_POLL"

    CR_PLAN=$(get_cr_plan "$ISSUE_NUM")

    if [ -n "$CR_PLAN" ] && echo "$CR_PLAN" | grep -qi "plan\|task\|phase\|step\|implementation"; then
      log "CodeRabbit plan received! (after ${POLL_COUNT} polls)"
      break
    fi

    log "  Poll $POLL_COUNT/$CR_PLAN_MAX_POLLS — no plan yet..."
  done

  if [ -z "$CR_PLAN" ]; then
    log "CodeRabbit did not generate a plan within timeout — proceeding without it"
    CR_PLAN="No CodeRabbit plan available. Use your own analysis to implement the fix."
  fi

  # Save the plan for reference
  echo "$CR_PLAN" > "$LOG_DIR/cr_plan_iter${i}.md"

  # ===========================================================================
  # PHASE 2: Implement fix using CodeRabbit plan + write tests
  # ===========================================================================
  log "--- Phase 2: Implement fix + write tests ---"

  IMPL_LOG="$LOG_DIR/ralph_${TIMESTAMP}_iter${i}_impl.log"

  claude --print --dangerously-skip-permissions \
    "You are working on the n-aible EdTech simulation platform.
You are currently on branch '${BASE_BRANCH}'.

READ CLAUDE.md first for full project context.

## CONTEXT
You are fixing GitHub Issue #${ISSUE_NUM}.
CodeRabbit has analyzed the codebase and generated the following implementation plan:

--- CODERABBIT PLAN ---
${CR_PLAN}
--- END PLAN ---

## WORKFLOW — follow these steps exactly:

### Step 1: Create feature branch
- Determine type from the issue: 'bug' or 'feature'
- Create: git checkout -b ralph-looped/<type>/<short-slug>
- Example: ralph-looped/bug/grading-not-working

### Step 2: Implement the fix
- Use CodeRabbit's plan as your primary guide
- Read all relevant code before making changes
- Make focused, minimal changes
- Do NOT modify .env files, docker-compose.yml, or infrastructure config
- Do NOT add new dependencies unless absolutely critical

### Step 3: Write tests
- For backend changes: add/update tests in backend/tests/
  - Unit tests for any new/changed functions
  - Integration tests for endpoint changes
  - Follow existing test patterns in tests/conftest.py
- For frontend changes: add tests if a testing framework is set up
- Tests should cover:
  - The happy path (fix works)
  - Edge cases mentioned in the issue
  - Regression (the old broken behavior no longer occurs)

### Step 3b: Visual / E2E testing with Playwright (for UI or API changes)
- If Playwright is NOT yet set up (no frontend/playwright.config.ts):
  1. cd frontend && pnpm add -D @playwright/test
  2. Create frontend/playwright.config.ts with baseURL http://localhost:3000
  3. Create frontend/e2e/ directory
- Write Playwright tests for your changes:
  - UI changes: test the affected page/component renders correctly,
    user interactions work, and visual state is correct
  - API-affecting changes: test via the frontend that the feature
    works end-to-end (e.g., form submission, data display)
  - Example test file: frontend/e2e/<feature-slug>.spec.ts
- Playwright test patterns to use:
  - page.goto(), page.click(), page.fill() for interactions
  - expect(page.locator(...)).toBeVisible() for visual assertions
  - expect(page).toHaveScreenshot() for visual regression (optional)
  - Use test.describe() to group related tests
- Run: cd frontend && npx playwright test --reporter=list 2>/dev/null || true
- NOTE: Playwright tests may fail if no dev server is running — that's OK,
  the tests themselves are the deliverable for CI to run later

### Step 4: Run all checks
- Backend: cd backend && python -m pytest tests/ -x -q 2>/dev/null || true
- Frontend: cd frontend && pnpm lint 2>/dev/null || true
- Playwright: cd frontend && npx playwright test --reporter=list 2>/dev/null || true

### Step 5: Commit (may be multiple commits)
- First commit — the fix:
    fix: <short description>

    Fixes #${ISSUE_NUM}
    Source: <Canny score=X / GitHub>

    <what was wrong and what you changed>

- Second commit — tests:
    test: add tests for <what was fixed>

    Covers: <list of test cases>

### Step 6: Push and create PR
- Push: git push -u origin <branch-name>
- Create PR targeting '${BASE_BRANCH}':
    gh pr create --base ${BASE_BRANCH} \\
      --title 'fix: <description>' \\
      --body '## Summary
    <what this PR does>

    Fixes #${ISSUE_NUM}

    ## Changes
    <bullet list of changes>

    ## Tests added
    <bullet list of new unit tests>
    <bullet list of new Playwright E2E tests if applicable>

    ## Test plan
    - [ ] Unit tests pass
    - [ ] Lint passes
    - [ ] Playwright E2E tests pass (if applicable)
    - [ ] Manual verification steps

    Generated by Ralph Loop iteration $i'
- Print at the end: PR_NUMBER=<number>

## RULES:
1. Follow CodeRabbit's plan closely but use your judgment if something seems off
2. Always write tests — this is mandatory, not optional
3. Do NOT fix issues marked 'complete' or 'closed'
4. If you cannot fix this issue, say SKIP_ITERATION and exit
5. Verify diff before PR: git diff ${BASE_BRANCH}...HEAD --stat
6. Use Railway CLI (railway logs, railway status) if you need deployment context for debugging" \
    2>&1 | tee "$IMPL_LOG"

  # Extract PR number
  PR_NUM=$(grep -oE 'PR_NUMBER=[0-9]+' "$IMPL_LOG" | tail -1 | cut -d= -f2 || echo "")

  if [ -z "$PR_NUM" ]; then
    PR_NUM=$(grep -oE 'pull/[0-9]+' "$IMPL_LOG" | tail -1 | grep -oE '[0-9]+' || echo "")
  fi

  if [ -z "$PR_NUM" ]; then
    log "!!! No PR created — skipping review phase"
    git checkout "$BASE_BRANCH" 2>/dev/null || true
    if [ "$i" -lt "$ITERATIONS" ]; then sleep "$PAUSE"; fi
    continue
  fi

  log "PR #${PR_NUM} created for Issue #${ISSUE_NUM}"

  # ===========================================================================
  # PHASE 3: CodeRabbit PR review loop
  # ===========================================================================
  log "--- Phase 3: CodeRabbit PR review cycle ---"
  log "Waiting ${CR_REVIEW_WAIT}s for first CodeRabbit review..."
  sleep "$CR_REVIEW_WAIT"

  REVIEW_ROUND=0
  while [ "$REVIEW_ROUND" -lt "$CR_MAX_ROUNDS" ]; do
    REVIEW_ROUND=$((REVIEW_ROUND + 1))
    log "--- Review round $REVIEW_ROUND / $CR_MAX_ROUNDS ---"

    CR_FEEDBACK=$(get_cr_pr_comments "$PR_NUM")

    # Check if there's actionable feedback (skip the summary/walkthrough comment)
    HAS_ACTIONABLE=$(echo "$CR_FEEDBACK" | python3 -c "
import sys
text = sys.stdin.read()
# CodeRabbit's summary comment always appears — look for actual issues
actionable_signals = ['suggestion', 'issue', 'bug', 'error', 'warning', 'consider', 'should', 'must', 'missing', 'incorrect', 'fix']
lower = text.lower()
found = any(s in lower for s in actionable_signals)
# But not if it's just the summary with no issues
if 'no issues found' in lower or 'lgtm' in lower or 'looks good' in lower:
    found = False
print('yes' if found else 'no')
" 2>/dev/null || echo "no")

    if [ "$HAS_ACTIONABLE" = "no" ] || [ -z "$CR_FEEDBACK" ]; then
      log "CodeRabbit has no actionable comments — moving on"
      break
    fi

    log "CodeRabbit left actionable feedback — launching Claude to address it"

    REVIEW_LOG="$LOG_DIR/ralph_${TIMESTAMP}_iter${i}_review${REVIEW_ROUND}.log"
    FEATURE_BRANCH=$(git branch --show-current)

    claude --print --dangerously-skip-permissions \
      "You are on branch '${FEATURE_BRANCH}' in the n-aible EdTech simulation platform.
There is an open PR #${PR_NUM} targeting '${BASE_BRANCH}' (fixing Issue #${ISSUE_NUM}).

CodeRabbit (automated code reviewer) has left the following feedback:

--- CODERABBIT FEEDBACK ---
${CR_FEEDBACK}
--- END FEEDBACK ---

## YOUR TASK
1. Read and understand each piece of CodeRabbit feedback
2. Make the necessary code changes to address ALL actionable feedback
3. If CodeRabbit suggests additional tests, write them
4. Run checks:
   - Backend: cd backend && python -m pytest tests/ -x -q 2>/dev/null || true
   - Frontend: cd frontend && pnpm lint 2>/dev/null || true
5. Commit: 'fix: address CodeRabbit review round ${REVIEW_ROUND}'
6. Push: git push

## RULES:
- Address ALL actionable feedback
- If feedback is a false positive or style nit, skip it but explain why
- Do NOT modify .env files, docker-compose.yml, or infrastructure config
- If CodeRabbit suggests tests you haven't written, write them now (unit tests AND Playwright E2E)
- Run Playwright tests too: cd frontend && npx playwright test --reporter=list 2>/dev/null || true
- Keep changes focused on the review feedback" \
      2>&1 | tee "$REVIEW_LOG" | tail -15

    log "Review round $REVIEW_ROUND complete"

    if [ "$REVIEW_ROUND" -lt "$CR_MAX_ROUNDS" ]; then
      log "Waiting ${CR_FOLLOWUP_WAIT}s for CodeRabbit re-review..."
      sleep "$CR_FOLLOWUP_WAIT"
    fi
  done

  # ===========================================================================
  # PHASE 4: CI gate and merge
  # ===========================================================================
  log "--- Phase 4: CI check and merge ---"
  log "Waiting 60s for CI checks..."
  sleep 60

  CI_PASSED=false
  for attempt in 1 2 3; do
    if ci_checks_pass "$PR_NUM"; then
      CI_PASSED=true
      break
    fi
    log "CI not passing yet (attempt $attempt/3) — waiting 60s..."
    sleep 60
  done

  if [ "$CI_PASSED" = true ]; then
    log "CI checks passed — squash merging PR #${PR_NUM}"
    gh pr merge "$PR_NUM" --squash --delete-branch 2>&1 | tee -a "$MASTER_LOG"
    log "PR #${PR_NUM} merged! Issue #${ISSUE_NUM} resolved."

    # Close the GitHub issue with implementation notes
    gh issue close "$ISSUE_NUM" --comment "$(cat <<EOF
## Resolved by Ralph Loop (iteration $i)

**PR:** #${PR_NUM} (merged)
**Branch:** ralph-looped

### What was done
- Issue analyzed and implementation planned via CodeRabbit
- Fix implemented with unit tests and Playwright E2E tests
- CodeRabbit review feedback addressed
- All CI checks passed before merge

$([ -n "$CANNY_POST_ID" ] && echo "**Canny Post:** https://n-aible.canny.io/admin/board/feedback/p/${CANNY_POST_ID}")
EOF
)" 2>/dev/null || true

    # Update Canny post: mark complete + add detailed comment linking everything
    if [ -n "$CANNY_POST_ID" ]; then
      PR_URL="https://github.com/${GH_REPO}/pull/${PR_NUM}"
      ISSUE_URL="https://github.com/${GH_REPO}/issues/${ISSUE_NUM}"
      update_canny_post "$CANNY_POST_ID" "complete" \
        "This has been fixed! Here are the details: GitHub Issue: ${ISSUE_URL} | Pull Request: ${PR_URL} | The fix has been merged and will be available in the next deployment from the ralph-looped branch."
      log "Canny post ${CANNY_POST_ID} marked complete with links"
    fi
  else
    log "!!! CI did not pass — leaving PR #${PR_NUM} open for manual review"

    # If Canny, update status to "under review" so it's not stuck as "in progress"
    if [ -n "$CANNY_POST_ID" ]; then
      update_canny_post "$CANNY_POST_ID" "under review" \
        "Automated fix attempted but CI checks did not pass. PR #${PR_NUM} is open for manual review: https://github.com/${GH_REPO}/pull/${PR_NUM}"
    fi
  fi

  # Return to base branch
  git checkout "$BASE_BRANCH"
  git pull origin "$BASE_BRANCH" 2>/dev/null || true

  log ""
  log "--- Iteration $i complete ---"

  if [ "$i" -lt "$ITERATIONS" ]; then
    log "--- Pausing ${PAUSE}s before next iteration ---"
    sleep "$PAUSE"
  fi
done

# =============================================================================
# SUMMARY
# =============================================================================
log ""
log "============================================================"
log "=== Ralph Loop COMPLETE — $ITERATIONS iterations ==="
log "=== $(date) ==="
log "============================================================"
log ""
log "Recent commits on ${BASE_BRANCH}:"
git log --oneline -"$ITERATIONS" 2>/dev/null | tee -a "$MASTER_LOG"
log ""
log "Open PRs needing manual review:"
gh pr list --base "$BASE_BRANCH" --state open 2>/dev/null | tee -a "$MASTER_LOG"
log ""
log "Full log: $MASTER_LOG"
