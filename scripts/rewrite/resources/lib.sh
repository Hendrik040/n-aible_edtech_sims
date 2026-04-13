#!/usr/bin/env bash
# ralph-rewrite-loop — shared shell helpers. Sourced by the main loop
# after config.sh. Every function here is side-effect-safe to redefine.
# shellcheck disable=SC2034,SC2155

# ===========================================================================
# Logging
# ===========================================================================
log() {
  local ts; ts=$(date +'%H:%M:%S')
  if [ -n "${MASTER_LOG:-}" ]; then
    printf '[%s] %s\n' "$ts" "$*" | tee -a "$MASTER_LOG"
  else
    printf '[%s] %s\n' "$ts" "$*"
  fi
}
die() { log "ERROR: $*"; exit 1; }

# ===========================================================================
# GitHub API helpers (all read against $GH_REPO)
# ===========================================================================
gh_issue_list_open() {
  gh issue list \
    --repo "$GH_REPO" --label "$LABEL" \
    --state open --limit 100 \
    --json number,title,body 2>/dev/null || echo "[]"
}

# Ready tickets = upstream deps all merged into $BASE_BRANCH. Emits
# "issue_num|ticket_id|title" rows sorted by ticket id, earliest first.
pick_ready_tickets() {
  local issues_json
  issues_json=$(gh_issue_list_open)
  python3 - "$issues_json" "$BASE_BRANCH" "$GH_REPO" <<'PY'
import json, re, subprocess, sys
issues = json.loads(sys.argv[1])
base   = sys.argv[2]
repo   = sys.argv[3]

TICKET_RE = re.compile(r"phase-(\d+)(?:\.(\d+))?")
DEP_RE    = re.compile(r"###\s*Depends on\s*\n(.*?)(?=\n###|\Z)", re.IGNORECASE | re.DOTALL)
NUM_RE    = re.compile(r"#(\d+)")

def ticket_id(title):
    m = TICKET_RE.search(title)
    return f"phase-{int(m.group(1))}.{int(m.group(2) or 0):02d}" if m else "zzz"

def deps(body):
    if not body:
        return []
    m = DEP_RE.search(body)
    return [int(n) for n in NUM_RE.findall(m.group(1))] if m else []

def dep_met(n):
    # issue closed AND its PR merged into base.
    r = subprocess.run(
        ["gh", "issue", "view", str(n), "--repo", repo, "--json", "state"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        return False
    try:
        if json.loads(r.stdout).get("state") != "CLOSED":
            return False
    except json.JSONDecodeError:
        return False
    p = subprocess.run(
        ["gh", "pr", "list", "--repo", repo,
         "--state", "merged", "--base", base,
         "--search", f"Fixes #{n} OR Closes #{n}",
         "--json", "number,body,title"],
        capture_output=True, text=True
    )
    if p.returncode != 0:
        return False
    try:
        prs = json.loads(p.stdout)
    except json.JSONDecodeError:
        return False
    for pr in prs:
        blob = (pr.get("body","") or "") + " " + (pr.get("title","") or "")
        if re.search(rf"(?:[Ff]ixes|[Cc]loses|[Rr]esolves)\s+#{n}\b", blob):
            return True
    return False

rows = []
for i in issues:
    blocked = [d for d in deps(i.get("body","") or "") if not dep_met(d)]
    if not blocked:
        rows.append((ticket_id(i["title"]), i["number"], i["title"]))
rows.sort()
for tid, n, t in rows:
    print(f"{n}|{tid}|{t}")
PY
}

pr_already_open_for() {
  local issue=$1
  gh pr list --repo "$GH_REPO" --base "$BASE_BRANCH" --state open \
    --search "Fixes #${issue}" --json number --jq '.[0].number' 2>/dev/null
}

get_cr_plan() {
  local issue=$1
  gh api "repos/${GH_REPO}/issues/${issue}/comments" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai"))
           | select(.body | test("Coding Plan|## Summary|Implementation Steps"; "i"))]
          | last | .body // ""' 2>/dev/null
}

get_cr_pr_comments() {
  local pr=$1
  local inline; inline=$(gh api "repos/${GH_REPO}/pulls/${pr}/comments" \
    --jq '.[] | select(.user.login | startswith("coderabbitai")) | "- " + .path + ": " + .body' 2>/dev/null)
  local summary; summary=$(gh pr view "$pr" --repo "$GH_REPO" --json comments \
    --jq '.comments[] | select(.author.login | startswith("coderabbitai")) | .body' 2>/dev/null)
  printf '%s\n%s\n' "$inline" "$summary"
}

count_cr_pr_comments() {
  local pr=$1
  local ic; ic=$(gh api "repos/${GH_REPO}/pulls/${pr}/comments" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai"))] | length' 2>/dev/null || echo 0)
  local pc; pc=$(gh pr view "$pr" --repo "$GH_REPO" --json comments \
    --jq '[.comments[] | select(.author.login | startswith("coderabbitai"))] | length' 2>/dev/null || echo 0)
  echo $((ic + pc))
}

cr_approved() {
  local pr=$1
  local n; n=$(gh api "repos/${GH_REPO}/pulls/${pr}/reviews" \
    --jq '[.[] | select(.user.login | startswith("coderabbitai")) | select(.state == "APPROVED")] | length' 2>/dev/null || echo 0)
  [ "$n" -gt 0 ]
}

ci_checks_pass() {
  local pr=$1
  local status; status=$(gh pr checks "$pr" --repo "$GH_REPO" 2>/dev/null || echo "PENDING")
  ! echo "$status" | grep -q "fail"
}

# ===========================================================================
# Worktree management
# ===========================================================================
refresh_anchor() {
  # Fast-forward the anchor onto origin/$BASE_BRANCH so every new worktree
  # starts from the latest integration-trunk state. Ff-only — never
  # clobbers anchor commits.
  git -C "$REPO_DIR" fetch --quiet origin "$BASE_BRANCH" "$ANCHOR_BRANCH" 2>/dev/null || true
  if git -C "$REPO_DIR" merge-base --is-ancestor \
        "origin/${ANCHOR_BRANCH}" "origin/${BASE_BRANCH}" 2>/dev/null; then
    log "anchor '${ANCHOR_BRANCH}' is behind '${BASE_BRANCH}' — fast-forwarding"
    git -C "$REPO_DIR" push --quiet origin \
      "origin/${BASE_BRANCH}:${ANCHOR_BRANCH}" 2>/dev/null \
      || log "  (ff-push failed — anchor may already be up to date)"
  fi
}

worktree_create() {
  # Create an isolated worktree off origin/$ANCHOR_BRANCH. Prints the
  # path on stdout.
  local ticket_id=$1
  local dir="${WORKTREE_BASE}/rewrite-${ticket_id}-$(date +%s)"
  git -C "$REPO_DIR" worktree add "$dir" "origin/$ANCHOR_BRANCH" --detach >/dev/null 2>&1 \
    || { log "worktree create failed for $ticket_id"; return 1; }
  echo "$dir"
}

worktree_cleanup() {
  local dir=$1
  [ -z "$dir" ] && return 0
  git -C "$REPO_DIR" worktree remove "$dir" --force >/dev/null 2>&1 \
    || rm -rf "$dir" 2>/dev/null
  git -C "$REPO_DIR" worktree prune >/dev/null 2>&1 || true
}

# ===========================================================================
# Slug generation (keep in sync with scripts/rewrite/migrate-to-ralph-looped.py)
# ===========================================================================
ticket_slug() {
  # Args: title
  python3 - "$1" <<'PY'
import re, sys
t = sys.argv[1].lower()
t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
skip = {"the","a","an","py","into","for","with","and","or","of"}
parts = [p for p in t.split("-") if p not in skip]
print(("-".join(parts)[:40]).strip("-"))
PY
}

feature_branch_for() {
  # Args: ticket_id, ticket_title
  echo "${FEATURE_PREFIX}/${1}-$(ticket_slug "$2")"
}

# ===========================================================================
# Prompt rendering (replaces {{VAR}} tokens from env, no shell interpolation)
# ===========================================================================
render_prompt() {
  # Args: prompt_template_path -> stdout is the rendered prompt.
  # Only replaces {{UPPERCASE_VAR}} tokens whose corresponding env var
  # is exported; leaves all other double-braced text untouched. Safe for
  # prompts that contain code examples with curly braces.
  python3 - "$1" <<'PY'
import os, re, sys
text = open(sys.argv[1]).read()
def repl(m):
    k = m.group(1)
    return os.environ.get(k, m.group(0))
print(re.sub(r"\{\{([A-Z_][A-Z0-9_]*)\}\}", repl, text))
PY
}

# ===========================================================================
# Claude invocation
# ===========================================================================
run_claude_in() {
  # Args: cwd, prompt_text_file, log_file
  local cwd=$1 prompt=$2 log=$3
  (cd "$cwd" && claude --print --dangerously-skip-permissions < "$prompt") \
    2>&1 | tee "$log"
}

# ===========================================================================
# Watchdog — kills any claude process older than CLAUDE_TIMEOUT_SEC
# ===========================================================================
start_watchdog() {
  (
    while true; do
      sleep 300
      # BSD awk (macOS) rejects chained ternaries — use if/else.
      ps -eo pid,etime,comm | awk -v max="$CLAUDE_TIMEOUT_SEC" '
        /claude/ {
          n = split($2, p, /[-:]/)
          if (n == 2)      { s = p[1]*60 + p[2] }
          else if (n == 3) { s = p[1]*3600 + p[2]*60 + p[3] }
          else if (n == 4) { s = p[1]*86400 + p[2]*3600 + p[3]*60 + p[4] }
          else             { s = 0 }
          if (s > max) print $1
        }
      ' | while read -r pid; do
        echo "WATCHDOG: killing hung claude PID $pid" >> "${MASTER_LOG:-/dev/stderr}"
        kill -TERM "$pid" 2>/dev/null; sleep 5; kill -KILL "$pid" 2>/dev/null
      done
    done
  ) &
  WATCHDOG_PID=$!
}

stop_watchdog() {
  [ -n "${WATCHDOG_PID:-}" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
}
