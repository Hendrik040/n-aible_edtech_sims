#!/usr/bin/env bash
# probe-api-contract.sh — diff-aware API contract probe.
#
# 1. Fetches the experimental-env OpenAPI spec (baseline — what the
#    deployed frontend consumes).
# 2. If a local backend is up on :8000, fetches its spec too and diffs.
# 3. Reads the current git diff, maps touched files to router
#    prefixes, and lists affected endpoints.
# 4. Prints a punch list: new / removed / shape-changed endpoints,
#    grouped so the caller knows which of them the frontend will
#    notice.
#
# Exit: 0 always (even on detected breaks) — the caller is responsible
# for deciding what to do. Exit 2 on prerequisite failure.

set -uo pipefail

WORKDIR="${CONTRACT_WORKDIR:-/tmp/api-contract}"
EXP_URL="${EXPERIMENTAL_OPENAPI_URL:-https://backend-experimental-246c.up.railway.app/openapi.json}"
LOCAL_URL="${LOCAL_OPENAPI_URL:-http://localhost:8000/openapi.json}"
BASE_REF="${API_CONTRACT_BASE_REF:-origin/ralph-looped}"

mkdir -p "$WORKDIR"

for bin in curl jq python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: required tool missing: $bin" >&2
    exit 2
  fi
done

# --- fetch specs ------------------------------------------------------------
echo "=== Fetching OpenAPI specs ==="
if ! curl -sfL --max-time 15 "$EXP_URL" -o "$WORKDIR/remote.json" 2>"$WORKDIR/remote.err"; then
  echo "  ❌ could not fetch experimental spec ($EXP_URL)"
  echo "     $(cat "$WORKDIR/remote.err" 2>/dev/null | head -1)"
  exit 2
fi
echo "  ✅ remote:  $EXP_URL  ($(wc -c < "$WORKDIR/remote.json") bytes)"

local_present=0
if curl -sfL --max-time 3 "$LOCAL_URL" -o "$WORKDIR/local.json" 2>"$WORKDIR/local.err"; then
  echo "  ✅ local:   $LOCAL_URL  ($(wc -c < "$WORKDIR/local.json") bytes)"
  local_present=1
else
  echo "  (no local backend on :8000 — will diff git-changed files against remote only)"
  echo ""
fi

# --- diff specs (only if both present) --------------------------------------
if [ "$local_present" = "1" ]; then
  echo ""
  echo "=== OpenAPI diff (local vs experimental) ==="
  python3 - "$WORKDIR/local.json" "$WORKDIR/remote.json" <<'PY'
import json, sys

local = json.load(open(sys.argv[1]))
remote = json.load(open(sys.argv[2]))

def ops(spec):
    out = {}
    for path, methods in spec.get("paths", {}).items():
        for method, meta in methods.items():
            out[f"{method.upper()} {path}"] = meta
    return out

L, R = ops(local), ops(remote)

added   = sorted(set(L) - set(R))
removed = sorted(set(R) - set(L))
changed = []
for key in sorted(set(L) & set(R)):
    # Compare response schemas (shape-breaking if any 2xx schema diverges)
    def norm(o):
        return json.dumps(o.get("responses", {}), sort_keys=True, default=str)
    if norm(L[key]) != norm(R[key]):
        changed.append(key)

if not (added or removed or changed):
    print("  ✅ no OpenAPI differences")
else:
    if added:
        print(f"  🟢 NEW in local ({len(added)}):")
        for k in added[:20]:
            print(f"    + {k}")
        if len(added) > 20:
            print(f"    … +{len(added)-20} more")
    if removed:
        print(f"  🔴 REMOVED from local ({len(removed)}):")
        for k in removed[:20]:
            print(f"    - {k}")
        if len(removed) > 20:
            print(f"    … +{len(removed)-20} more")
    if changed:
        print(f"  🟡 RESPONSE-SHAPE CHANGED ({len(changed)}):")
        for k in changed[:20]:
            print(f"    ~ {k}")
        if len(changed) > 20:
            print(f"    … +{len(changed)-20} more")
PY
fi

# --- diff-aware endpoint discovery -----------------------------------------
echo ""
echo "=== Affected endpoints (from git diff vs ${BASE_REF}) ==="

python3 - "$WORKDIR/remote.json" "$BASE_REF" <<'PY'
import json, os, re, subprocess, sys

remote_spec = json.load(open(sys.argv[1]))
base_ref = sys.argv[2]

try:
    diff_out = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True, capture_output=True, text=True
    ).stdout
except subprocess.CalledProcessError:
    diff_out = ""
changed_files = [f.strip() for f in diff_out.splitlines() if f.strip()]
if not changed_files:
    # Fall back to working-tree diff if no commits yet.
    diff_out = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "--"],
        capture_output=True, text=True
    ).stdout
    changed_files = [f.strip() for f in diff_out.splitlines() if f.strip()]

# File-path → router-prefix map. Keep this conservative; adding an
# entry is cheap, missing one just means fewer endpoints flagged.
FILE_TO_PREFIX = [
    ("backend/api/auth.py",                "/api/auth/users"),
    ("backend/modules/auth/",              "/api/auth/users"),
    ("backend/api/simulation.py",          "/api/simulation"),
    ("backend/modules/simulation/",        "/api/simulation"),
    ("backend/api/publishing.py",          "/api/publishing"),
    ("backend/modules/publishing/",        "/api/publishing"),
    ("backend/api/pdf_processing.py",      "/api/pdf-processing"),
    ("backend/modules/pdf_processing/",    "/api/pdf-processing"),
    ("backend/api/professor/",             "/professor"),
    ("backend/modules/professor/",         "/professor"),
    ("backend/api/student/",               "/student"),
    ("backend/modules/student/",           "/student"),
    ("backend/modules/cohorts/",           "/professor/cohorts"),
    ("backend/modules/notifications/",     "/professor/notifications"),
    ("backend/api/admin",                  "/api/admin"),
    ("backend/common/db/models/",          "*"),   # touches response shapes everywhere
    ("backend/common/db/base.py",          "*"),
]

affected_prefixes = set()
schema_wide_change = False
for f in changed_files:
    for path, prefix in FILE_TO_PREFIX:
        if f == path or f.startswith(path):
            if prefix == "*":
                schema_wide_change = True
            else:
                affected_prefixes.add(prefix)

remote_paths = list(remote_spec.get("paths", {}).keys())

if schema_wide_change:
    print("  ⚠ diff touches common/db models — ANY endpoint using those models")
    print("    could have a response-shape change. Re-run contract tests broadly.")
    print("")

if not affected_prefixes and not schema_wide_change:
    print("  (no router / schema files in diff — no endpoints flagged)")
    sys.exit(0)

shown = 0
for prefix in sorted(affected_prefixes):
    matches = [p for p in remote_paths if p.startswith(prefix)]
    print(f"  affected by diff → prefix {prefix}  ({len(matches)} endpoints)")
    for p in matches[:6]:
        methods = ",".join(m.upper() for m in remote_spec["paths"][p].keys())
        print(f"    - {methods:<20} {p}")
        shown += 1
    if len(matches) > 6:
        print(f"    … +{len(matches)-6} more under {prefix}")

print("")
print(f"  → run: cd backend && python -m pytest tests/contract/ -q")
print("         (or tests/modules/<mod>/test_router.py for the affected modules)")
PY
