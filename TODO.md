# TODO — Daytona Code Sandbox

## Sandbox Lifecycle & Resource Management

- **Aggressive sandbox cleanup on simulation end/reset**: Currently sandboxes auto-delete after 24h, but repeated testing can hit the 30GiB disk limit before that. Need to ensure `delete_sandbox()` is called on every exit path:
  - Simulation complete (done)
  - Simulation reset by student (needs check)
  - Simulation reset by professor re-publishing
  - Browser tab close / session timeout
  - Server restart (orphaned sandboxes)

- **Startup cleanup of orphaned sandboxes**: On app startup, query `UserProgress` rows with non-null `sandbox_id` where `simulation_status` is `completed` or stale (no activity for >2h), and delete those sandboxes.

- **Lower auto-delete interval**: Consider reducing `auto_delete_interval` from 1440 (24h) to 360 (6h) or less, since simulations rarely span that long.

- **Lower auto-stop interval**: Consider reducing `auto_stop_interval` from 60 to 15-30 minutes for dev/testing tiers.

- **Sandbox creation failure UX**: When sandbox creation fails (disk limit, API error), the "temporarily unavailable" banner shows but the student has no way to retry. Add a "Retry" button or auto-retry on next code execution attempt.

## Data File Handling

- **CSV preview for xlsx files**: The preview generation uses openpyxl on the backend. Need to re-upload data files after adding openpyxl to regenerate previews for existing xlsx files.

- **Large file handling**: No size limit on data file uploads currently. Add a max file size (e.g., 10MB) in the SceneCard UI and backend validation.

## Professor Test Page

- **Split-pane resizing**: The code editor split is fixed at 50/50. Add a draggable divider like the left panel has.

## Code Editor

- **Persistent code state**: Code typed in the editor is lost on tab switch or page refresh. Consider saving to localStorage or backend.

- **Multiple file support**: Currently single-file editor. The mockup shows a file tab (`analysis.py`). Future: support multiple files.

- **Syntax error highlighting**: CodeMirror shows syntax highlighting but no linting. Consider adding Python linting.
