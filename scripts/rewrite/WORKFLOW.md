# Ralph Rewrite Loop — Workflow

One iteration picks one ticket from `#430..#451` and lands one PR on
`ralph-looped`. All skills referenced below live under
`.claude/skills/` and auto-invoke on description-match — the orchestrator
never has to call them explicitly.

For the flow diagrams of the E2E test that runs inside step 6b, see
[.claude/skills/e2e-simulation-flow/DIAGRAMS.md](../../.claude/skills/e2e-simulation-flow/DIAGRAMS.md).

```
           [outer loop picks earliest ready ticket #430..#451]
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. FETCH from GitHub                                                        │
│    ticket body (scope, files, tests) + CodeRabbit "Coding Plan" comment     │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. IMPLEMENT (YOLO)  in worktree off `ralph-looped-rewrite-agent-sdk`       │
│    claude --print --dangerously-skip-permissions                            │
│    feature branch: ralph-looped-rewrite/phase-X.Y-<slug>                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. LOCAL REVIEW        🛠 skill: code-review                                 │
│    `coderabbit review --agent` on local diff ─┐                             │
│    iterate until clean (max N rounds)          └─ claude fixes ─ loop back  │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. PUSH + OPEN PR  targeting `ralph-looped`  (body: "Fixes #<issue>")       │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. PR-LEVEL VALIDATION (async, same branch — push fix commits, not new PRs) │
│                                                                             │
│   ┌──────────────────────┐              ┌──────────────────────────────┐    │
│   │ 5a. CodeRabbit PR bot│              │ 5b. 🛠 railway-deploy-check  │    │
│   │     inline + summary │              │     railway logs --env        │    │
│   │     GitHub review    │              │     experimental  (bot+app)  │    │
│   └──────────┬───────────┘              └──────────────┬───────────────┘    │
│              │ findings                                │                    │
│              └──────────┬─────────────────────────────┘                    │
│                         ▼                                                   │
│        any finding? ── yes ──▶ 🛠 autofix skill applies → push → re-review   │
│                         │ no                                                │
└─────────────────────────┼───────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. TESTING SKILLS                                                           │
│                                                                             │
│   ┌─────────────────────────┐   ┌──────────────────────────────────────┐    │
│   │ 6a. 🛠 api-contract-test│   │ 6b. 🛠 e2e-simulation-flow (+ neon- │    │
│   │   diff live openapi vs  │   │     postgres for DB validation)      │    │
│   │   local, map diff→      │   │     Flow 1 professor + Flow 2 student│    │
│   │   endpoints             │   │     against EXPERIMENTAL env         │    │
│   └───────────┬─────────────┘   └────────────────────┬─────────────────┘    │
│               │                                       │                     │
│               └─────────────┬────────────────────────┘                     │
│                             │                                               │
│          ┌──────────────────┴──────────────────┐                           │
│          │ (if diff touches sandbox code only) │                           │
│          │  🛠 daytona-sandbox — probe + exec  │                           │
│          └──────────────────┬──────────────────┘                           │
│                             ▼                                               │
│         red → back to step 2 (fix + push); green → ↓                        │
└─────────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 7. MERGE into ralph-looped   gh pr merge --squash → "Fixes #N" auto-closes  │
└─────────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼   (merge-only; no Canny entry for closed-unmerged PRs)
┌─────────────────────────────────────────────────────────────────────────────┐
│ 8. PHASE E — Canny changelog (non-fatal)                                    │
│    claude --print with post-to-canny prompt → non-tech {title, body}        │
│    POST canny.io/api/v1/posts/create (authorID=CANNY_ADMIN_ID,              │
│                                        boardID=CANNY_BOARD_ID,              │
│                                        title="{CANNY_TITLE_PREFIX} ...")    │
│    gh pr comment <PR> with Canny URL (linkback for admin dashboard)         │
└─────────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
                  outer loop: next ready ticket
```

## Skills referenced

| 🛠 | Skill | Role |
| --- | --- | --- |
| step 3 | [code-review](../../.claude/skills/code-review/SKILL.md) | local CodeRabbit CLI review before push |
| step 5 | [autofix](../../.claude/skills/autofix/SKILL.md) | apply CodeRabbit PR-bot feedback on the same branch |
| step 5b | [railway-deploy-check](../../.claude/skills/railway-deploy-check/SKILL.md) | experimental env deploy health |
| step 6a | [api-contract-test](../../.claude/skills/api-contract-test/SKILL.md) | frontend-facing OpenAPI contract diff + per-endpoint tests |
| step 6b | [e2e-simulation-flow](../../.claude/skills/e2e-simulation-flow/SKILL.md) | full professor + student round-trip |
| step 6b | [neon-postgres](../../.claude/skills/neon-postgres/SKILL.md) | DB validation used by E2E |
| cond. | [daytona-sandbox](../../.claude/skills/daytona-sandbox/SKILL.md) | only if the diff touches sandbox-related code |
| step 8 | [resources/post-to-canny.py](resources/post-to-canny.py) + [resources/prompts/post-to-canny.md](resources/prompts/post-to-canny.md) | non-tech Canny changelog entry after squash merge |

## Environment scope

Everything runs against **experimental** — never `staging-v2`, never `production-v3`:

| Surface | Value |
| --- | --- |
| Railway environment | `experimental` |
| Neon branch | `experimental-v2` |
| Neon project | `super-cherry-83189326` |
| Backend URL | `https://backend-experimental-246c.up.railway.app` |

## Merge-time invariants

- PR target is always `ralph-looped` (not `production-v3`).
- PR body contains `Fixes #<issue>` so the original `#430..#451` ticket auto-closes on merge.
- Feature branch name: `ralph-looped-rewrite/phase-X.Y-<slug>`.
- All 7 upstream dependency PRs must already be merged into `ralph-looped` before a ticket becomes "ready" (checked by the outer loop).
