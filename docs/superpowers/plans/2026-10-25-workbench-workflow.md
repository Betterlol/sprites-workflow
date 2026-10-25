# Sprite Workbench Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make disk edits recoverable, allow project settings changes, resolve concurrent config edits in the browser, and show progress with safe cancellation for long work.

**Architecture:** Add an incremental, project-local history journal around image-changing domain operations; expose guarded restoration to browser and CLI. Keep settings and conflict merging as explicit browser drafts, with existing revision checks on save. Run long exports as cancellable server jobs that publish phase and item progress without weakening the project lock.

**Tech Stack:** Python 3.10+, FastAPI, Pillow, native JavaScript modules.

**Spec:** `docs/superpowers/specs/2026-10-25-workbench-improvements-design.md`

## Global Constraints

- Existing artwork is shared human/agent data. Tests use temporary projects and synthetic images; do not change `assets/` or `workspaces/dafeiyu/`.
- Preserve current config and asset revision checks, cross-process project lock, project-root path containment and approved/manual sprite locations.
- No new runtime dependency or frontend build step.
- Run `python -m unittest discover -s tests -v`, `node tests/test_workbench_model.mjs` and `node tests/test_workbench_session.mjs` before each commit.

## Design calls

- History stores only files affected by a completed image operation, including the pre-operation `pipeline.json`; it does not copy the whole project on every edit. Restoring requires the current config and asset revisions, checks that affected files still match the recorded post-operation state, and creates a new recoverable history entry. History stays local to the project and is not included in normal resource exports.
- Project settings edit the saved draft. Changing canvas or anchor marks source-derived sprites as stale; existing processed pixels are never silently resized or replaced. The UI explains that sources must be reapplied and manually authored frames may need replacement before export.
- Three-way config merge uses the last saved browser snapshot as base. Independent object fields merge automatically; arrays are atomic. For each conflict the user chooses the local or disk value. The result remains an unsaved draft and is still subject to the latest server revision check.
- Cancellation occurs at safe boundaries between export items. An encoding step already in progress finishes before cancellation takes effect. Completed files are only offered for download when the job succeeds.

## Review Focus

- Failed writes must not leave a misleading completed history version or partly restored files.
- Restore must reject external changes, path traversal and links leaving the project, including edits to manual sprites.
- Canvas changes must keep normalized anchor coordinates and pixel coordinates consistent.
- Merge must distinguish deletion from an explicit null value and must not silently overwrite two edits to the same array.
- Cancelling one export must not affect another project's job or the active project's committed files.

---

### Task 1: Incremental history and restore

**Files:** Create `tools/sprite_pipeline/history.py`; modify `workbench.py`, `server.py`, `projects_cli.py`, web UI, `tests/test_projects.py`, `tests/test_workbench.py`, docs.

**Interfaces:** `ProjectHistory.transaction(operation, paths)` captures a pre-operation snapshot of selected files and records their post-operation hashes. `Project.history()` lists versions. `Project.restore(version_id, revision, asset_revision)` restores a version under the project lock and returns a fresh snapshot. Browser and `projects.py` expose the same restore operation.

- [ ] Write failing tests for apply, import, delete, version listing, restoration, external modification rejection and traversal protection.
- [ ] Run focused tests and inspect the expected failures.
- [ ] Implement journal and guarded restore, then wire browser and CLI controls.
- [ ] Run focused tests and the three required suites; inspect diff and commit `feat: add recoverable sprite history`.

### Task 2: Project settings editor

**Files:** `tools/sprite_pipeline/web/index.html`, `app.js`, `style.css`, `tests/test_workbench_session.mjs`, `tests/test_workbench.py`, docs.

**Interfaces:** Settings form changes `project.name`, `frame_size`, normalized anchor x/y and derived pixel anchor within the draft. Existing save and undo handle the edit. The form previews stale-source impact and requires an explicit confirmation for canvas changes.

- [ ] Write failing tests for settings values, anchor consistency, undo and preserved processed files.
- [ ] Run the focused tests and inspect the expected failures.
- [ ] Implement the form, state updates and warning copy.
- [ ] Run focused tests and the three required suites; inspect diff and commit `feat: edit project canvas and anchor`.

### Task 3: Three-way conflict merge

**Files:** Create `tools/sprite_pipeline/web/merge.js`; modify `app.js`, `index.html`, `style.css`, `tests/test_workbench_model.mjs`, `tests/test_workbench_session.mjs`, docs.

**Interfaces:** `mergeDraft(base, local, disk)` returns a proposed config and conflicts with JSON paths. The browser presents local/disk choices, rebases onto the disk revision, and keeps the result unsaved until explicit Save.

- [ ] Write failing pure-model and session tests for independent edits, conflicting values, arrays, deletions and a second disk change before save.
- [ ] Run focused tests and inspect the expected failures.
- [ ] Implement merge model and conflict dialog.
- [ ] Run focused tests and the three required suites; inspect diff and commit `feat: merge concurrent project drafts`.

### Task 4: Export progress and cancellation

**Files:** `tools/sprite_pipeline/workbench.py`, `server.py`, `web/app.js`, `web/index.html`, `tests/test_workbench.py`, `tests/test_workbench_session.mjs`, docs.

**Interfaces:** Start/poll/cancel/download endpoints manage per-job state. Export emits progress after each completed action or archive phase, checks cancellation between safe items, and never writes project output files. Browser displays current phase and count, and cancel stops future work.

- [ ] Write failing tests for progress, cancellation, isolation and completed ZIP compatibility.
- [ ] Run focused tests and inspect the expected failures.
- [ ] Implement server job lifecycle, domain progress callbacks and UI progress/cancel.
- [ ] Run focused tests and the three required suites; inspect diff and commit `feat: track and cancel long exports`.

### Task 5: Review and real-project read-only verification

- [ ] Review the full branch against the spec and fix Important findings with new regression tests.
- [ ] Open the real project read-only to verify settings, history display and conflict controls without applying, restoring, importing or exporting its artwork.
- [ ] Report commits, tests, remaining limitations and how to restart the local server for user testing.
