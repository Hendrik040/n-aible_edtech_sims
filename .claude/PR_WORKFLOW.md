# PR Workflow Rules for Claude Code

## Branch Rules

1. **NEVER push directly to `production`**
2. **NEVER open PRs targeting `production`**
3. **Always open PRs targeting `develop-v2`**

## PR + CodeRabbit Review Process

### Step 1: Create PR
- Create PR from feature/bug branch → `develop-v2`
- Write clear title and description

### Step 2: Wait for CodeRabbit
- **First PR review: Wait 5 minutes** before checking for comments
- **Incremental reviews (after fixes): Wait 3 minutes** before checking
- CodeRabbit will post comments on the PR

### Step 3: Address Comments
- Read all CodeRabbit comments
- Make necessary code changes
- Commit and push fixes

### Step 4: Repeat
- Wait 3 minutes for CodeRabbit to re-review
- Address any new comments
- Repeat until no more comments

### Step 5: Merge
- Wait for user approval
- Only merge after explicit user confirmation

## Timing Summary

| Action | Wait Time |
|--------|-----------|
| First PR created | 5 minutes |
| After pushing fixes | 3 minutes |

## Important Learnings

1. **Always verify the actual diff** before creating a PR
   - Compare against the correct base branch: `git diff develop-v2...HEAD --stat`
   - Branches may already be merged/rebased, resulting in minimal or no changes

2. **CodeRabbit will flag mismatched titles** if the PR title doesn't reflect actual changes

3. **Fetch before comparing** to ensure you have latest remote state:
   ```bash
   git fetch origin develop-v2
   git log origin/develop-v2..HEAD --oneline
   ```

## Commands Reference

```bash
# Check PR status
gh pr view <PR_NUMBER> --json comments,reviews,state

# Get CodeRabbit summary comment
gh pr view <PR_NUMBER> --json comments --jq '.comments[] | select(.author.login == "coderabbitai") | .body'

# Get inline review comments
gh api repos/Hendrik040/n-aible_edtech_sims/pulls/<PR_NUMBER>/comments

# Update PR base branch
gh pr edit <PR_NUMBER> --base develop-v2

# Check actual diff before PR
git fetch origin develop-v2
git diff origin/develop-v2...HEAD --stat
```

## Future: Git Worktrees
- Will implement git worktrees workflow for parallel development
- Allows working on multiple branches simultaneously without switching
