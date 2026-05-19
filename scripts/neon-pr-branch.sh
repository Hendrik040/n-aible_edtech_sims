#!/bin/bash
# ============================================================================
# Neon PR Database Branching — Create/delete Neon DB branches for PRs
# ============================================================================
# Usage:
#   ./scripts/neon-pr-branch.sh create <pr-number>
#   ./scripts/neon-pr-branch.sh delete <pr-number>
#
# Creates Neon branches forked from experimental-v2 for isolated PR testing.
# Prints the DATABASE_URL connection string on create.
# ============================================================================

set -euo pipefail

NEONCTL="/opt/homebrew/bin/neonctl"
PROJECT_ID="super-cherry-83189326"
ORG_ID="org-shiny-resonance-67239217"
PARENT_BRANCH_ID="br-square-brook-afa604nb"

usage() {
  echo "Usage: $0 {create|delete} <pr-number>"
  exit 1
}

if [ $# -lt 2 ]; then
  usage
fi

COMMAND="$1"
PR_NUMBER="$2"
BRANCH_NAME="pr-${PR_NUMBER}"

case "$COMMAND" in
  create)
    # Check if branch already exists
    EXISTING=$("$NEONCTL" branches list \
      --project-id "$PROJECT_ID" \
      --org-id "$ORG_ID" \
      --output json 2>/dev/null \
      | python3 -c "
import json, sys
branches = json.load(sys.stdin)
# Handle both list-of-dicts and dict-with-branches-key formats
if isinstance(branches, dict):
    branches = branches.get('branches', [])
for b in branches:
    if b.get('name') == '${BRANCH_NAME}':
        print(b.get('id', 'exists'))
        break
" 2>/dev/null || echo "")

    if [ -n "$EXISTING" ]; then
      echo "Neon branch '${BRANCH_NAME}' already exists (id: ${EXISTING})" >&2
    else
      echo "Creating Neon branch '${BRANCH_NAME}' from experimental-v2..." >&2
      "$NEONCTL" branches create \
        --project-id "$PROJECT_ID" \
        --org-id "$ORG_ID" \
        --parent "$PARENT_BRANCH_ID" \
        --name "$BRANCH_NAME" \
        --output json >/dev/null 2>&1
      echo "Neon branch '${BRANCH_NAME}' created." >&2
    fi

    # Get and print the connection string (this is the DATABASE_URL)
    DATABASE_URL=$("$NEONCTL" connection-string \
      --project-id "$PROJECT_ID" \
      --org-id "$ORG_ID" \
      --branch "$BRANCH_NAME" 2>/dev/null)

    echo "$DATABASE_URL"
    ;;

  delete)
    # Check if branch exists before attempting delete
    EXISTING=$("$NEONCTL" branches list \
      --project-id "$PROJECT_ID" \
      --org-id "$ORG_ID" \
      --output json 2>/dev/null \
      | python3 -c "
import json, sys
branches = json.load(sys.stdin)
if isinstance(branches, dict):
    branches = branches.get('branches', [])
for b in branches:
    if b.get('name') == '${BRANCH_NAME}':
        print(b.get('id', 'exists'))
        break
" 2>/dev/null || echo "")

    if [ -z "$EXISTING" ]; then
      echo "Neon branch '${BRANCH_NAME}' does not exist — nothing to delete." >&2
      exit 0
    fi

    echo "Deleting Neon branch '${BRANCH_NAME}'..." >&2
    "$NEONCTL" branches delete "$BRANCH_NAME" \
      --project-id "$PROJECT_ID" \
      --org-id "$ORG_ID" 2>/dev/null || true
    echo "Neon branch '${BRANCH_NAME}' deleted." >&2
    ;;

  *)
    usage
    ;;
esac
