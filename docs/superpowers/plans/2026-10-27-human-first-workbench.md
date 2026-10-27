# Human-first Workbench Implementation Plan

> Execute inline using executing-plans. The user approved implementing the three concept screens and testing the resulting web UI.

**Goal:** Deliver a usable light-themed editor organized around character references, slicing, frame adjustment, actions, and export.

**Architecture:** Retain the existing project domain, persistence and conflict checks. Split source editing into slicing and adjustment views; give slicing a read-only extraction preview independent of processing. Reuse the existing action/review editor and exports. Introduce no configuration migration or generated artwork.

**Tech Stack:** FastAPI, Pillow, native JavaScript modules, Canvas 2D, CSS; no frontend build.

**Spec:** Approved concept images in `docs/designs/2026-10-27-workbench-concepts/` and the conversation. Images are visual references, not promises that every illustrated feature already exists.

## Global Constraints

- Preserve existing assets, workspace artwork, configurations, unsaved draft protection, undo/redo and revision checks.
- Work in the existing checkout on `codex/human-first-workbench`; no automatic commits or publishing.
- Keep settings and saved/applied distinctions truthful. Adjustment still applies one source group; incremental per-frame processing and metadata migration are future stages.
- Do not show nonfunctional Agent-generation controls. Reference comparison identifies the current idle action frame rather than declaring an approved artistic baseline.
- All writing/processing tests use temporary projects and synthetic images.

## Review Focus

- Slicing must work even when downstream processing rules would fail.
- Switching slicing/adjustment with in-flight previews must not show the wrong preview type.
- Empty projects, absent references and imported-only frames remain usable.
- Existing save/import/export, undo and external-conflict handling remain reachable.
- Panels must fit a desktop viewport and remain accessible at narrow widths.

### Task 1: Separate slicing preview

Files: `workbench.py`, `server.py`, `tests/test_workbench.py`.
- [x] Add and run a failing test: extraction preview returns native-size slices without invoking processing and without writing project files.
- [x] Add optional `stage=extract|process` to preview; preserve the existing default response and source identities.
- [x] Verify focused tests and invalid-stage rejection.

### Task 2: Workflow and editor shell

Files: `web/index.html`, `web/app.js`, `web/studio.css`, `tests/test_workbench_session.mjs`.
- [x] Test switching source stages preserves edits and scopes preview requests correctly.
- [x] Implement five workflow entries, contextual slicing/adjustment inspectors, raw slice tray, reference comparison and action/review switch.
- [x] Apply the light/teal design, larger controls, thumbnail navigation and responsive panels.
- [x] Keep ordinary project saving explicit and processing application within adjustment.

### Task 3: Verification and handoff

- [x] Run `python -m unittest discover -s tests -v`, `node tests/test_workbench_model.mjs`, `node tests/test_workbench_session.mjs`.
- [x] Exercise the actual browser using temporary synthetic material; inspect desktop and narrow-screen screenshots, console errors, save/reopen, slicing and adjustment.
- [x] Review the diff; document current UI and remaining group-processing limitation.
- [x] Start a separate local server for the real workspace and report the tested URL.

## Progress

- Plan recorded before implementation. Existing untracked workspace projects and browser artifacts are user data and are preserved.

- Completed: 131 Python tests and both JavaScript suites passed. Real Chromium checks covered region edits, stage isolation, frame adjustments, save/reopen, playback, review navigation, ZIP download, empty projects and 1920/1440/1024/390px layouts. Browser console is clean.
- Fresh code review found a missing snapshot-triggered slicing refresh; fixed and verified. Browser QA exposed a home-navigation preview lifetime error; added a failing regression test before fixing it.
- Local workspace server started at http://127.0.0.1:8765. No existing artwork or pipeline configuration was modified. User acceptance of interaction remains pending.
