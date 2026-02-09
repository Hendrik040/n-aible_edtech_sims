# Open PR Command

Opens a pull request following the team's workflow conventions.

## Workflow

1. **Verify changes exist** - Check git status for uncommitted/unpushed changes
2. **Stage and commit** - Stage relevant files and create a conventional commit
3. **Push to remote** - Push branch to origin
4. **Create PR** - Open PR targeting `develop-v2` (NEVER `production`)
5. **Wait for CodeRabbit** - Wait 5 minutes for initial review
6. **Report status** - Show PR URL and CodeRabbit feedback

## Rules

- **NEVER** target `production` branch
- **ALWAYS** target `develop-v2` branch
- Use conventional commit format: `feat:`, `fix:`, `chore:`, etc.
- Include `Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>` in commits

## Timing

| Action | Wait Time |
|--------|-----------|
| First PR review | 5 minutes |
| After pushing fixes | 3 minutes |

## Usage

```
/open-pr
/open-pr "Custom PR title"
```

---

$ARGUMENTS: Optional custom PR title

$INSTRUCTIONS:

You are creating a pull request. Follow these steps exactly:

1. First, check current git status and what branch you're on:
```bash
git status
git branch --show-current
```

2. If there are uncommitted changes, stage and commit them:
   - Use conventional commit format (feat/fix/chore/etc.)
   - Add `Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>`

3. Push the branch to origin:
```bash
git push -u origin $(git branch --show-current)
```

4. Create PR targeting develop-v2 (NEVER production!):
```bash
gh pr create --title "<title>" --body "<body>" --base develop-v2
```

5. Report the PR URL to the user

6. Start 5-minute timer, then check for CodeRabbit comments:
```bash
sleep 300
gh pr view <PR_NUMBER> --json comments --jq '.comments[] | select(.author.login == "coderabbitai") | .body'
```

7. If CodeRabbit has actionable comments:
   - Summarize the feedback for the user
   - Ask if they want you to address the comments

8. If addressing comments:
   - Make the fixes
   - Commit and push
   - Wait 3 minutes for re-review
   - Repeat until no more actionable comments

IMPORTANT: If no arguments provided, infer the PR title from the commit messages or branch name.
