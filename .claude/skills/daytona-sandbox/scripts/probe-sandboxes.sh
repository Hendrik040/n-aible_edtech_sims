#!/usr/bin/env bash
# probe-sandboxes.sh — read-only snapshot of current Daytona state.
# No mutating calls; safe to run in any automated context.
#
# Exit: 0 on success, 2 if prerequisites missing.

set -uo pipefail

if ! command -v daytona >/dev/null 2>&1; then
  echo "ERROR: daytona CLI not installed" >&2
  exit 2
fi
# `sandbox list` is the only auth probe that works for BOTH browser-login
# and API-key auth modes. `organization list` fails under API-key auth with
# "organization commands are not available when using API key authentication"
# even when everything this skill actually uses works fine.
if ! daytona sandbox list >/dev/null 2>&1; then
  echo "ERROR: daytona CLI not authed (run: daytona login, or set DAYTONA_API_KEY)" >&2
  exit 2
fi

# ---- Sandboxes -----------------------------------------------------------
echo "=== Sandboxes ==="
if ! sb_json=$(daytona sandbox list -f json 2>&1); then
  echo "  could not list sandboxes:"
  echo "$sb_json" | sed 's/^/    /'
  exit 1
fi

echo "$sb_json" | python3 - <<'PY'
import json, sys, collections

try:
    data = json.loads(sys.stdin.read() or "[]")
except json.JSONDecodeError:
    print("  (empty or non-JSON response)")
    sys.exit(0)
if not data:
    print("  (no sandboxes)")
    sys.exit(0)

states = collections.Counter(s.get("state", "?") for s in data)
print(f"  total: {len(data)}  by state: " +
      ", ".join(f"{k}={v}" for k, v in sorted(states.items())))

# Call out unhealthy states loudly.
bad = [s for s in data if s.get("state") in
       ("error", "failed", "pulling-image", "build-failed")]
if bad:
    print(f"  ⚠ {len(bad)} sandbox(es) in unhealthy state:")
    for s in bad[:5]:
        print(f"    - {s.get('id','?')[:12]}  state={s.get('state')}"
              f"  created={s.get('createdAt','?')}")

# Show first 8 rows so Claude has concrete anchors to reference.
print("  sample rows:")
for s in data[:8]:
    sid = (s.get("id") or "?")[:12]
    state = s.get("state", "?")
    snap  = s.get("snapshot") or s.get("snapshotId") or "-"
    auto  = s.get("autoStopInterval", "?")
    print(f"    {sid}  state={state:10s}  snapshot={snap}  auto-stop={auto}m")
PY

# ---- Snapshots -----------------------------------------------------------
echo ""
echo "=== Snapshots ==="
if snap_json=$(daytona snapshot list -f json 2>&1); then
  echo "$snap_json" | python3 - <<'PY'
import json, sys
try:
    data = json.loads(sys.stdin.read() or "[]")
except json.JSONDecodeError:
    print("  (empty or non-JSON response)")
    sys.exit(0)
if not data:
    print("  (no snapshots)")
    sys.exit(0)
print(f"  total: {len(data)}")
for s in data[:6]:
    name = s.get("name") or s.get("id") or "?"
    size = s.get("size") or s.get("imageSize") or "?"
    print(f"    {name}  size={size}")
PY
else
  echo "  (snapshot list not available: $snap_json)"
fi
