#!/usr/bin/env bash
# experimental-health.sh — pre-flight for the E2E flow.
# Read-only sanity checks against the experimental environment only.
# Exits 0 if ready to run, 2 if any surface is not usable.

set -uo pipefail

BASE_URL="${E2E_BASE_URL:-https://backend-experimental-246c.up.railway.app}"
NEON_PROJECT="${NEON_PROJECT_ID:-super-cherry-83189326}"
NEON_BRANCH="${NEON_BRANCH:-experimental-v2}"

fail=0
pass() { echo "  ✅ $*"; }
warn() { echo "  ⚠ $*"; fail=1; }

echo "=== E2E pre-flight (experimental env) ==="

# 1. Backend
if curl -sfL --max-time 5 "${BASE_URL}/health" >/dev/null 2>&1; then
  pass "backend reachable @ ${BASE_URL}"
else
  warn "backend NOT reachable @ ${BASE_URL}/health"
fi

# 2. Backend openapi (proves routes registered, not just container alive)
if curl -sfL --max-time 10 "${BASE_URL}/openapi.json" -o /dev/null 2>&1; then
  pass "openapi.json served"
else
  warn "openapi.json NOT served — backend may be starting up"
fi

# 3. Neon branch
if command -v neonctl >/dev/null 2>&1; then
  if neonctl branches list --project-id "$NEON_PROJECT" 2>/dev/null \
     | grep -q "$NEON_BRANCH"; then
    pass "neon branch '${NEON_BRANCH}' found in project ${NEON_PROJECT}"
  else
    warn "neon branch '${NEON_BRANCH}' not found — did you authenticate? (neonctl auth)"
  fi
else
  warn "neonctl CLI not installed"
fi

# 4. Daytona (non-fatal — only needed if the simulation under test uses code_challenge scenes)
if command -v daytona >/dev/null 2>&1 \
   && daytona organization list >/dev/null 2>&1; then
  pass "daytona CLI authed (sandbox checks available if needed)"
else
  echo "  (daytona CLI missing or not authed — code_challenge scenes will not be testable)"
fi

# 5. Sample PDF fixture in the worktree
if [ -f "scripts/test-fixtures/HBR_CaseStudy.pdf" ]; then
  pass "sample PDF found @ scripts/test-fixtures/HBR_CaseStudy.pdf"
else
  warn "sample PDF missing (expected scripts/test-fixtures/HBR_CaseStudy.pdf)"
fi

# 6. Python + requests
if python3 -c 'import requests' 2>/dev/null; then
  pass "python3 with requests available"
else
  warn "python3 'requests' module missing — install with: pip install requests"
fi

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "pre-flight FAILED — fix the warnings above before running run-e2e.py"
  exit 2
fi
echo ""
echo "pre-flight OK — safe to run run-e2e.py"
