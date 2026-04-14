#!/usr/bin/env bash
# ralph-rewrite-loop — configuration constants.
# Sourced by the main loop and lib.sh. Every value is env-overridable
# so the loop stays runnable in CI, locally, or under debug.
# shellcheck disable=SC2034

# --- repo + branches -------------------------------------------------------
GH_REPO="${GH_REPO:-Hendrik040/n-aible_edtech_sims}"
BASE_BRANCH="${BASE_BRANCH:-ralph-looped}"
ANCHOR_BRANCH="${ANCHOR_BRANCH:-ralph-looped-rewrite-agent-sdk}"
FEATURE_PREFIX="${FEATURE_PREFIX:-ralph-looped-rewrite}"

# --- issue filter ----------------------------------------------------------
LABEL="${LABEL:-rewrite-agent-sdk}"

# --- loop cadence ----------------------------------------------------------
ITERATIONS="${ITERATIONS:-5}"
PAUSE_BETWEEN="${PAUSE_BETWEEN:-30}"

# --- CodeRabbit timing -----------------------------------------------------
CR_PLAN_POLL_SEC="${CR_PLAN_POLL_SEC:-60}"
CR_PLAN_MAX_POLLS="${CR_PLAN_MAX_POLLS:-20}"
CR_REVIEW_WAIT_SEC="${CR_REVIEW_WAIT_SEC:-1200}"
CR_FOLLOWUP_WAIT_SEC="${CR_FOLLOWUP_WAIT_SEC:-1200}"
CR_MAX_ROUNDS="${CR_MAX_ROUNDS:-4}"

# --- CI polling ------------------------------------------------------------
CI_POLL_SEC="${CI_POLL_SEC:-60}"
CI_MAX_POLLS="${CI_MAX_POLLS:-10}"

# --- Claude ----------------------------------------------------------------
CLAUDE_TIMEOUT_SEC="${CLAUDE_TIMEOUT_SEC:-2700}"

# --- Paths (derived — do not override unless you know why) -----------------
_CFG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOURCES_DIR="$_CFG_DIR"
PROMPTS_DIR="${RESOURCES_DIR}/prompts"
REPO_DIR="$(cd "${RESOURCES_DIR}/../../.." && pwd)"
WORKTREE_BASE="${WORKTREE_BASE:-$(cd "$REPO_DIR/.." && pwd)/work-trees}"
LOG_DIR="${LOG_DIR:-$REPO_DIR/scripts/rewrite/logs}"

# --- Pipeline telemetry (PR-B) ---------------------------------------------
# Loop POSTs phase-transition events to the admin dashboard's ingest
# endpoint. Both vars must be set for events to fire; otherwise the
# loop runs silently without telemetry (no error, no block). Values
# are grep-loaded from .env (same token also lives on Railway so the
# backend can verify the bearer).
_load_env_var() {
  local key=$1
  for file in "${REPO_DIR}/.env" "${REPO_DIR}/backend/.env"; do
    [ -f "$file" ] || continue
    local val
    val=$(grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'")
    if [ -n "$val" ]; then
      printf '%s' "$val"
      return 0
    fi
  done
  return 0
}
RALPH_EVENT_URL="${RALPH_EVENT_URL:-$(_load_env_var RALPH_EVENT_URL)}"
RALPH_EVENT_TOKEN="${RALPH_EVENT_TOKEN:-$(_load_env_var RALPH_EVENT_TOKEN)}"
