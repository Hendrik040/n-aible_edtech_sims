---
name: Rewrite (Agent SDK) ticket
about: Human-authored ticket for the Claude Agent SDK rewrite track. Matches the format scripts/rewrite/create-issues.py generates so the Ralph loop and verifier can pick it up.
title: "[rewrite-agent-sdk] phase-X.Y: <short title>"
labels: ["rewrite-agent-sdk", "type-rewrite"]
assignees: []
---

<!-- Also add a label for the phase number, e.g. `phase-2`. -->
<!-- ticket-id: phase-X.Y -->

## Ticket: `phase-X.Y` — <short title>

**Target branch:** `rewrite/agent-sdk` (NOT `production-v3`)

### Depends on
<!-- One bullet per upstream issue, e.g. `- #123 (phase-1.1)`. Use `_None_`
     if this ticket is a root. The loop parses these lines to gate
     ticket-readiness. -->
- _None — ready to pick up immediately._

### Scope
<!-- Grounded prose: exactly what to build. This is what CodeRabbit sees
     when it plans. -->

### Files this ticket may touch
<!-- Comma-separated glob list. The verifier rejects diffs outside this
     list — be accurate, not aspirational. -->
`backend_v2/path/to/file.py, backend_v2/tests/path/to/test_file.py`

### Unit tests required
<!-- Semicolon-separated list of test function names. The verifier greps
     each name in the matching test file. Use `none` for scaffold-only
     tickets. -->
test_happy_path; test_edge_case; test_error_handling

### Contract tests required
<!-- Same format as above. `none` unless this ticket touches a
     frontend-visible endpoint. -->
none

### Verification (merge gate)
<!-- The exact commands the loop runs via scripts/rewrite/verify-ticket.sh.
     State them concretely — `uv run pytest <paths> -q --cov=<mod>
     --cov-fail-under=85` etc. The loop will not merge the PR unless
     verify-ticket.sh exits 0. -->

### Non-goals
<!-- What this ticket is explicitly NOT doing. The verifier does not
     enforce these, but they keep CodeRabbit and Claude from wandering. -->
