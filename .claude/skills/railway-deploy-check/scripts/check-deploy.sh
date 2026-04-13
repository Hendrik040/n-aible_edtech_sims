#!/usr/bin/env bash
# check-deploy.sh — tail Railway logs for services in the `experimental`
# environment and surface the failure signature when a deploy broke.
#
# Usage: check-deploy.sh [service...]
#        (default services: Backend Frontend)
#
# Exit: 0 if every inspected service is clean, 1 if any service shows
# a failure marker in its recent logs, 2 on prerequisite failure
# (CLI missing / not authed / project not linked).
#
# Security: never reads ~/.railway/config.json, never prints auth
# tokens, never accepts a token as an argument. The CLI handles auth
# via its own config and env; this script stays out of that path.

set -uo pipefail

ENV_NAME="experimental"
SERVICES=("$@")
if [ ${#SERVICES[@]} -eq 0 ]; then
  SERVICES=(Backend Frontend)
fi

# --- prerequisite checks ---------------------------------------------------
if ! command -v railway >/dev/null 2>&1; then
  echo "ERROR: railway CLI not installed (see https://docs.railway.com/guides/cli)" >&2
  exit 2
fi
if ! railway whoami >/dev/null 2>&1; then
  echo "ERROR: railway CLI not authed. Run: railway login" >&2
  exit 2
fi

# Redact any bearer-token / secret-looking strings before printing log
# output. Defensive only — Railway logs normally don't emit these, but
# a misconfigured app could.
redact() {
  sed -E \
    -e 's/(Bearer )[A-Za-z0-9._\-]{20,}/\1***REDACTED***/g' \
    -e 's/(ey[A-Za-z0-9_\-]{20,}\.ey[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,})/***JWT_REDACTED***/g' \
    -e 's/(sk-[A-Za-z0-9_\-]{20,})/sk-***REDACTED***/g' \
    -e 's/(rw_[A-Za-z0-9_\-]{20,})/rw_***REDACTED***/g'
}

# --- deploy-log scan -------------------------------------------------------
# Failure markers we treat as "deploy broke or app crashed":
FAIL_RE='(Traceback \(most recent|ERROR |FATAL |Build failed|Deployment failed|Deploy failed|exited with code [1-9]|ModuleNotFoundError|SyntaxError|ImportError|npm ERR!|error TS[0-9]+:|Error: Cannot find module)'

overall_exit=0
for svc in "${SERVICES[@]}"; do
  echo "=== ${svc} @ ${ENV_NAME} ==="

  if ! logs=$(railway logs --environment "$ENV_NAME" -s "$svc" --lines 200 2>&1); then
    echo "  STATUS: ❌ could not fetch logs"
    echo "${logs}" | redact | sed 's/^/    /'
    overall_exit=1
    continue
  fi

  # Strip obvious ANSI color codes before matching.
  clean=$(printf '%s\n' "$logs" | sed $'s/\x1b\\[[0-9;]*[a-zA-Z]//g')

  if printf '%s\n' "$clean" | grep -qE "$FAIL_RE"; then
    echo "  STATUS: ❌ failure markers detected"
    echo "  ────────── log excerpt (context around failure) ──────────"
    # Print 30 lines before and 10 lines after the first match, capped
    # at 60 lines total so the summary stays scannable.
    printf '%s\n' "$clean" \
      | grep -E -B 30 -A 10 "$FAIL_RE" \
      | head -60 \
      | redact \
      | sed 's/^/    /'
    echo "  ───────────────────────────────────────────────────────────"
    overall_exit=1
  else
    echo "  STATUS: ✅ green (no failure markers in last 200 lines)"
  fi
done

exit "$overall_exit"
