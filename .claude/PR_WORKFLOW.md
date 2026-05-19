# PR Workflow — moved to skill

**Superseded** by the `pr-review-workflow` skill at
[`skills/pr-review-workflow/SKILL.md`](skills/pr-review-workflow/SKILL.md).

The skill encodes the full current workflow — pre-open CLI health
probes, PR body + test-plan shape, the 15-min CodeRabbit follow-up
cron, comment-closure discipline, merge gates, post-merge Railway
verification (not just `/health`), and the narrow conditions when
admin-merge is legitimate.

The old instructions in this file targeted `develop-v2` and were
missing the merge-discipline + cron-follow-up + post-merge-verify
steps that we evolved during the rewrite-agent-sdk track. Kept as a
redirect so stale links don't 404.
