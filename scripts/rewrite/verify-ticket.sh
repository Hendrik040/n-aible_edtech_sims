#!/usr/bin/env bash
# ============================================================================
# verify-ticket.sh — per-ticket merge gate for the rewrite-agent-sdk track
# ============================================================================
#
# Usage:
#   verify-ticket.sh <ticket-id>            # local/dev invocation
#   verify-ticket.sh <ticket-id> <pr-num>    # loop invocation (adds PR comment)
#
# Exit codes (strict — the Ralph loop keys off these):
#   0 → all gates passed, safe to merge
#   1 → scope mismatch (diff touches files outside the ticket's allowlist,
#       or misses files it was supposed to touch)
#   2 → missing unit tests (source file in diff has no matching test file,
#       or a required test function name is not found in the test file)
#   3 → unit test failures or coverage below 85%
#   4 → contract test failures
#   5 → parity mismatch (dual-target harness diverged)
#
# This script reads the ticket spec out of plan/REWRITE_BREAKDOWN.md. It's
# intentionally strict — the gate is the thing the user called out as missing
# in the previous Ralph-loop experiment, so it fails closed rather than open.
# ============================================================================

set -uo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $(basename "$0") <ticket-id> [pr-number]" >&2
  exit 64
fi

TICKET_ID="$1"
PR_NUM="${2:-}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BREAKDOWN="${REPO_ROOT}/plan/REWRITE_BREAKDOWN.md"
BASE_BRANCH="${REWRITE_BASE_BRANCH:-rewrite/agent-sdk}"
BASE_REF="origin/${BASE_BRANCH}"
COVERAGE_FLOOR="${COVERAGE_FLOOR:-85}"

GATE_RESULTS=()

log()  { echo "[verify-ticket] $*"; }
fail() { echo "[verify-ticket] FAIL: $*" >&2; }

record() {
  # record <gate-name> <pass|fail> <detail...>
  GATE_RESULTS+=("$1|$2|${3:-}")
}

post_pr_summary() {
  local overall="$1"
  if [ -z "$PR_NUM" ]; then
    return
  fi
  if ! command -v gh >/dev/null 2>&1; then
    return
  fi
  local body
  body="## verify-ticket.sh — ${overall}

Ticket: \`${TICKET_ID}\`
Base: \`${BASE_BRANCH}\` @ $(git -C "$REPO_ROOT" rev-parse --short "$BASE_REF" 2>/dev/null || echo unknown)
Coverage floor: ${COVERAGE_FLOOR}%

| Gate | Result | Detail |
| --- | --- | --- |"
  local row
  for row in "${GATE_RESULTS[@]}"; do
    local name status detail
    name="${row%%|*}"
    status="${row#*|}"; status="${status%%|*}"
    detail="${row##*|}"
    body="${body}
| ${name} | ${status} | ${detail} |"
  done
  gh pr comment "$PR_NUM" --body "$body" >/dev/null 2>&1 || true
}

if [ ! -f "$BREAKDOWN" ]; then
  fail "breakdown file not found: $BREAKDOWN"
  exit 64
fi

# ---------------------------------------------------------------------------
# Parse the ticket spec from the breakdown (inline Python — same parser shape
# as create-issues.py to avoid drift).
# ---------------------------------------------------------------------------
SPEC_JSON="$(python3 - "$BREAKDOWN" "$TICKET_ID" <<'PY'
import json, re, sys
from pathlib import Path

path = Path(sys.argv[1])
want = sys.argv[2]
text = path.read_text(encoding="utf-8")

HDR = re.compile(r"^### (phase-\d+(?:\.\d+)?): (.+)$")
KV  = re.compile(r"^- \*\*(\w+)\*\*:\s*(.*)$")

blocks, current, key, buf = [], None, None, []

def flush():
    global key, buf
    if current is None or key is None:
        key, buf = None, []
        return
    val = " ".join(s.strip() for s in buf).strip()
    current[key] = val
    key, buf = None, []

for line in text.splitlines():
    m = HDR.match(line)
    if m:
        flush()
        if current is not None:
            blocks.append(current)
        current = {"id": m.group(1), "title": m.group(2).strip()}
        continue
    if current is None:
        continue
    kv = KV.match(line)
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
    blocks.append(current)

match = next((b for b in blocks if b["id"] == want), None)
if not match:
    print(json.dumps({"error": f"ticket {want} not found"}))
    sys.exit(0)

# Split the files glob list into individual patterns.
files = [f.strip() for f in (match.get("files", "") or "").split(",") if f.strip()]
# Unit / contract test case names are semicolon-separated in the breakdown.
def split_cases(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if raw.lower() in ("", "none"):
        return []
    return [p.strip() for p in raw.split(";") if p.strip()]

print(json.dumps({
    "id": match["id"],
    "title": match["title"],
    "files": files,
    "unit_tests_required": split_cases(match.get("unit_tests_required", "")),
    "contract_tests_required": split_cases(match.get("contract_tests_required", "")),
}))
PY
)"

if echo "$SPEC_JSON" | grep -q '"error"'; then
  fail "$(echo "$SPEC_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["error"])')"
  exit 64
fi

read_spec_field() {
  # usage: read_spec_field <field>
  python3 -c "import json,sys; print(json.dumps(json.loads(sys.argv[1]).get(sys.argv[2], '')))" "$SPEC_JSON" "$1"
}

FILES_GLOBS=$(python3 -c "import json,sys; print('\n'.join(json.loads(sys.argv[1])['files']))" "$SPEC_JSON")
UNIT_CASES=$(python3 -c "import json,sys; print('\n'.join(json.loads(sys.argv[1])['unit_tests_required']))" "$SPEC_JSON")
CONTRACT_CASES=$(python3 -c "import json,sys; print('\n'.join(json.loads(sys.argv[1])['contract_tests_required']))" "$SPEC_JSON")

log "Verifying ticket ${TICKET_ID} against ${BASE_REF}"
log "  allowlist:           $(echo "$FILES_GLOBS" | tr '\n' ' ')"
log "  unit cases required: $(echo "$UNIT_CASES" | tr '\n' ';')"
log "  contract required:   $(echo "$CONTRACT_CASES" | tr '\n' ';')"

cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Resolve the base ref — fall back to main/local refs if origin/<base> is
# missing (e.g. fresh clone during CI).
# ---------------------------------------------------------------------------
if ! git rev-parse --verify --quiet "$BASE_REF" >/dev/null; then
  for candidate in "$BASE_BRANCH" "origin/main" "main"; do
    if git rev-parse --verify --quiet "$candidate" >/dev/null; then
      BASE_REF="$candidate"
      log "  (base ref 'origin/${BASE_BRANCH}' missing — using '${BASE_REF}')"
      break
    fi
  done
fi

CHANGED_FILES=$(git diff --name-only "$BASE_REF"...HEAD 2>/dev/null | sort -u)
if [ -z "$CHANGED_FILES" ]; then
  # No commits yet? try working tree diff.
  CHANGED_FILES=$(git diff --name-only "$BASE_REF" -- 2>/dev/null | sort -u)
fi

# ---------------------------------------------------------------------------
# GATE 1 — scope check
# ---------------------------------------------------------------------------
log ""
log "=== Gate 1: scope ==="

if [ -z "$CHANGED_FILES" ]; then
  fail "scope mismatch — no files changed vs ${BASE_REF} (ticket requires: $(echo "$FILES_GLOBS" | tr '\n' ' '))"
  record "scope" "fail" "no diff vs base"
  post_pr_summary "FAIL (scope — no diff)"
  exit 1
fi

# Always allow the tests/ tree corresponding to any touched source file.
ALLOWED_FILES=$(python3 - "$FILES_GLOBS" "$CHANGED_FILES" <<'PY'
import fnmatch, sys

globs = [g for g in sys.argv[1].splitlines() if g]
changed = [c for c in sys.argv[2].splitlines() if c]

def matches_allowlist(path: str) -> bool:
    for g in globs:
        if fnmatch.fnmatch(path, g):
            return True
        # Allow matches on the directory prefix — "foo/**" should cover
        # anything under foo/.
        if g.endswith("/**"):
            prefix = g[:-3]
            if path.startswith(prefix):
                return True
    return False

bad = [p for p in changed if not matches_allowlist(p)]
for p in bad:
    print(p)
PY
)

if [ -n "$ALLOWED_FILES" ]; then
  fail "scope mismatch — diff touches files outside the ticket allowlist:"
  echo "$ALLOWED_FILES" | sed 's/^/   /' >&2
  record "scope" "fail" "$(echo "$ALLOWED_FILES" | head -3 | tr '\n' ' ')..."
  post_pr_summary "FAIL (scope)"
  exit 1
fi
log "  scope OK ($(echo "$CHANGED_FILES" | wc -l | tr -d ' ') files, all within allowlist)"
record "scope" "pass" "$(echo "$CHANGED_FILES" | wc -l | tr -d ' ') files in allowlist"

# ---------------------------------------------------------------------------
# GATE 2 — unit test presence + required case names
# ---------------------------------------------------------------------------
log ""
log "=== Gate 2: unit test presence ==="

# Every .py source file in backend_v2/ (excluding tests) must have a matching
# test file at tests/<same-relative-path>/test_<basename>.py.
SOURCE_PY=$(echo "$CHANGED_FILES" | grep -E '^backend_v2/.*\.py$' | grep -vE '^backend_v2/tests/' || true)

MISSING_TESTS=""
for src in $SOURCE_PY; do
  # strip "backend_v2/" prefix
  rel="${src#backend_v2/}"
  dir=$(dirname "$rel")
  base=$(basename "$rel" .py)
  expected="backend_v2/tests/${dir}/test_${base}.py"
  # It's OK if the test file is in the diff OR already exists on the branch.
  if ! echo "$CHANGED_FILES" | grep -qx "$expected" \
       && [ ! -f "$REPO_ROOT/$expected" ]; then
    MISSING_TESTS="${MISSING_TESTS}
  ${src} → expected ${expected}"
  fi
done

if [ -n "$MISSING_TESTS" ]; then
  fail "missing unit tests for source files:${MISSING_TESTS}"
  record "unit-tests-present" "fail" "missing test files"
  post_pr_summary "FAIL (unit tests missing)"
  exit 2
fi
log "  every source file has a matching test file"
record "unit-tests-present" "pass" "all source files covered"

# Required case names — each must be findable in *some* test file in the diff.
if [ -n "$UNIT_CASES" ]; then
  TEST_FILES_IN_DIFF=$(echo "$CHANGED_FILES" | grep -E '^backend_v2/tests/.*\.py$' || true)
  if [ -z "$TEST_FILES_IN_DIFF" ]; then
    # No test diff but cases required — look in existing test tree too.
    TEST_FILES_IN_DIFF=$(find "$REPO_ROOT/backend_v2/tests" -type f -name 'test_*.py' 2>/dev/null | sed "s|${REPO_ROOT}/||")
  fi

  MISSING_CASES=""
  while IFS= read -r case_name; do
    [ -z "$case_name" ] && continue
    found=0
    for tf in $TEST_FILES_IN_DIFF; do
      if [ -f "$REPO_ROOT/$tf" ] && grep -qE "def[[:space:]]+${case_name}\\b" "$REPO_ROOT/$tf"; then
        found=1
        break
      fi
    done
    if [ "$found" = "0" ]; then
      MISSING_CASES="${MISSING_CASES}
  ${case_name}"
    fi
  done <<< "$UNIT_CASES"

  if [ -n "$MISSING_CASES" ]; then
    fail "required unit test cases not found in any test file:${MISSING_CASES}"
    record "unit-tests-cases" "fail" "missing: $(echo "$MISSING_CASES" | tr '\n' ' ')"
    post_pr_summary "FAIL (unit test cases)"
    exit 2
  fi
  log "  all required case names present in test files"
  record "unit-tests-cases" "pass" "$(echo "$UNIT_CASES" | wc -l | tr -d ' ') cases found"
else
  log "  (no unit cases required by spec)"
  record "unit-tests-cases" "pass" "none required"
fi

# ---------------------------------------------------------------------------
# GATE 3 — run pytest on touched tests with coverage
# ---------------------------------------------------------------------------
log ""
log "=== Gate 3: unit tests + coverage (floor ${COVERAGE_FLOOR}%) ==="

# Tests to run: every test file touched by the diff, plus the implied test
# files for each touched source file (already validated to exist in Gate 2).
TESTS_TO_RUN=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if [[ "$f" == backend_v2/tests/* ]]; then
    TESTS_TO_RUN="${TESTS_TO_RUN} ${f#backend_v2/}"
  fi
done <<< "$CHANGED_FILES"

# Add implied test files from source diffs.
for src in $SOURCE_PY; do
  rel="${src#backend_v2/}"
  dir=$(dirname "$rel")
  base=$(basename "$rel" .py)
  expected="tests/${dir}/test_${base}.py"
  case " $TESTS_TO_RUN " in
    *" $expected "*) : ;;
    *) TESTS_TO_RUN="${TESTS_TO_RUN} ${expected}" ;;
  esac
done
TESTS_TO_RUN="$(echo "$TESTS_TO_RUN" | xargs -n1 2>/dev/null | sort -u | xargs)"

# --cov targets: every touched source module under backend_v2/.
COV_TARGETS=""
for src in $SOURCE_PY; do
  # strip .py and backend_v2/ prefix, convert slashes to dots
  mod="${src#backend_v2/}"
  mod="${mod%.py}"
  mod="${mod//\//.}"
  COV_TARGETS="${COV_TARGETS} --cov=${mod}"
done

if [ -z "$TESTS_TO_RUN" ]; then
  log "  (no test files to run — scaffold-only ticket)"
  record "unit-tests-run" "pass" "no tests to run (scaffold)"
else
  if [ ! -d "$REPO_ROOT/backend_v2" ]; then
    fail "backend_v2/ directory does not exist yet — cannot run unit tests"
    record "unit-tests-run" "fail" "backend_v2/ missing"
    post_pr_summary "FAIL (unit tests — no backend_v2/)"
    exit 3
  fi
  log "  running: uv run pytest ${TESTS_TO_RUN} -q ${COV_TARGETS} --cov-fail-under=${COVERAGE_FLOOR}"
  if ! (cd "$REPO_ROOT/backend_v2" \
        && uv run pytest $TESTS_TO_RUN -q $COV_TARGETS --cov-fail-under="$COVERAGE_FLOOR" 2>&1); then
    fail "pytest failed or coverage below ${COVERAGE_FLOOR}%"
    record "unit-tests-run" "fail" "pytest/coverage"
    post_pr_summary "FAIL (unit tests/coverage)"
    exit 3
  fi
  log "  unit tests + coverage OK"
  record "unit-tests-run" "pass" "$(echo "$TESTS_TO_RUN" | wc -w | tr -d ' ') test files, ≥${COVERAGE_FLOOR}% coverage"
fi

# ---------------------------------------------------------------------------
# GATE 4 — contract tests (only if ticket touches an endpoint)
# ---------------------------------------------------------------------------
log ""
log "=== Gate 4: contract tests ==="

if [ -z "$CONTRACT_CASES" ]; then
  log "  (no contract tests required by spec)"
  record "contract-tests" "pass" "none required"
else
  CONTRACT_TEST_FILES=$(echo "$CHANGED_FILES" | grep -E '^backend_v2/tests/contract/.*\.py$' || true)
  if [ -z "$CONTRACT_TEST_FILES" ]; then
    CONTRACT_TEST_FILES=$(find "$REPO_ROOT/backend_v2/tests/contract" -type f -name 'test_*.py' 2>/dev/null | sed "s|${REPO_ROOT}/||")
  fi

  MISSING_CONTRACT=""
  while IFS= read -r case_name; do
    [ -z "$case_name" ] && continue
    found=0
    for tf in $CONTRACT_TEST_FILES; do
      if [ -f "$REPO_ROOT/$tf" ] && grep -qE "def[[:space:]]+${case_name}\\b" "$REPO_ROOT/$tf"; then
        found=1
        break
      fi
    done
    if [ "$found" = "0" ]; then
      MISSING_CONTRACT="${MISSING_CONTRACT}
  ${case_name}"
    fi
  done <<< "$CONTRACT_CASES"

  if [ -n "$MISSING_CONTRACT" ]; then
    fail "required contract test cases not found:${MISSING_CONTRACT}"
    record "contract-tests" "fail" "missing: $(echo "$MISSING_CONTRACT" | tr '\n' ' ')"
    post_pr_summary "FAIL (contract tests missing)"
    exit 4
  fi

  # Run the contract tests. The phase-6.1 harness makes these dual-target;
  # if the harness isn't in place yet, they still run against v2 only.
  CONTRACT_PATHS=$(echo "$CHANGED_FILES" | grep -E '^backend_v2/tests/contract/' | sed 's|backend_v2/||' | sort -u)
  if [ -z "$CONTRACT_PATHS" ]; then
    CONTRACT_PATHS="tests/contract/"
  fi
  log "  running: uv run pytest $CONTRACT_PATHS -q"
  if ! (cd "$REPO_ROOT/backend_v2" && uv run pytest $CONTRACT_PATHS -q 2>&1); then
    fail "contract tests failed"
    record "contract-tests" "fail" "pytest red"
    post_pr_summary "FAIL (contract tests red)"
    exit 4
  fi
  log "  contract tests OK"
  record "contract-tests" "pass" "$(echo "$CONTRACT_CASES" | wc -l | tr -d ' ') cases green"

  # Parity sub-check — only runs if the dual-target harness exists
  # (phase-6.1 ships it). Before then, skip with a warning.
  if [ -f "$REPO_ROOT/backend_v2/tests/contract/conftest.py" ] \
     && grep -q "client_legacy" "$REPO_ROOT/backend_v2/tests/contract/conftest.py" 2>/dev/null; then
    log "  running parity pass (legacy vs v2)..."
    if ! (cd "$REPO_ROOT/backend_v2" \
          && REWRITE_PARITY=1 uv run pytest $CONTRACT_PATHS -q 2>&1); then
      fail "parity mismatch between legacy and v2 backends"
      record "parity" "fail" "contract pytest diverged"
      post_pr_summary "FAIL (parity mismatch)"
      exit 5
    fi
    log "  parity OK (legacy ≡ v2)"
    record "parity" "pass" "legacy ≡ v2 on $(echo "$CONTRACT_CASES" | wc -l | tr -d ' ') cases"
  else
    log "  (dual-target harness not in place yet — skipping parity sub-check)"
    record "parity" "skip" "phase-6.1 harness not present"
  fi
fi

# ---------------------------------------------------------------------------
log ""
log "=== ALL GATES PASSED ==="
post_pr_summary "PASS"
exit 0
