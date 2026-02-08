# Git Worktree Workflow

## Directory Structure

```
/Users/hendrikkrack/Desktop/n-aible/
├── n-aible_edtech_sims/           # Main repo (develop-v2) - has the real .git folder
└── n-aible-worktrees/             # All worktrees go here
    ├── begin-button-ui/           # Worktree for UI improvement
    ├── my-first-tree/             # Test worktree
    └── <future-worktrees>/
```

## Setting Up a New Worktree

### 1. Create the worktree
```bash
# From the main repo directory
cd /Users/hendrikkrack/Desktop/n-aible/n-aible_edtech_sims

# Create worktree with new branch based on develop-v2
git worktree add -b <branch-name> ../n-aible-worktrees/<folder-name> origin/develop-v2
```

### 2. Copy environment files (REQUIRED - not tracked by git)
```bash
# Copy backend .env
cp /Users/hendrikkrack/Desktop/n-aible/n-aible_edtech_sims/backend/.env \
   /Users/hendrikkrack/Desktop/n-aible/n-aible-worktrees/<folder-name>/backend/.env

# Copy frontend .env
cp /Users/hendrikkrack/Desktop/n-aible/n-aible_edtech_sims/frontend/.env \
   /Users/hendrikkrack/Desktop/n-aible/n-aible-worktrees/<folder-name>/frontend/.env
```

### 3. Install dependencies
```bash
# Navigate INTO the worktree
cd /Users/hendrikkrack/Desktop/n-aible/n-aible-worktrees/<folder-name>

# Backend dependencies
cd backend
uv sync

# Frontend dependencies
cd ../frontend
pnpm install
```

## Working in a Worktree

### Always `cd` INTO the worktree first!
```bash
# WRONG - you're in the parent folder
cd /Users/hendrikkrack/Desktop/n-aible
git status  # ❌ "fatal: not a git repository"

# RIGHT - you're in the worktree
cd /Users/hendrikkrack/Desktop/n-aible/n-aible-worktrees/begin-button-ui
git status  # ✅ Works!
```

### Running the app
```bash
cd /Users/hendrikkrack/Desktop/n-aible/n-aible-worktrees/<folder-name>

# Terminal 1: Backend
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && pnpm dev
```

## Managing Worktrees

### List all worktrees
```bash
git worktree list
```

### Remove a worktree (when done with the feature)
```bash
git worktree remove /Users/hendrikkrack/Desktop/n-aible/n-aible-worktrees/<folder-name>
```

### Prune stale worktrees
```bash
git worktree prune
```

## Current Active Worktrees

| Folder | Branch | Purpose |
|--------|--------|---------|
| `n-aible_edtech_sims` | `develop-v2` | Main development |
| `begin-button-ui` | `ui/improve-begin-button-visibility` | Make begin button more visible |
| `my-first-tree` | `test-work-tree` | Test worktree |

## Important Notes

1. **The main repo owns `.git`** - don't delete the main repo or all worktrees break
2. **Each worktree = different branch** - you cannot checkout the same branch in two worktrees
3. **`.env` files must be copied manually** - they're gitignored
4. **`node_modules` and `venv` are per-worktree** - run install in each
5. **Commits are shared** - a commit in any worktree is visible to all (same repo)
