# Sprite QA Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce compact animation inspection artifacts from processed frames without task-specific capture scripts.

**Architecture:** Add a focused `sprite_pipeline.qa` renderer and expose it through `projects.py qa`. Reuse `action_steps` and `review_steps`; do not write into project art directories.

**Tech Stack:** Python, Pillow, unittest, existing sprite pipeline.

**Spec:** `docs/superpowers/specs/2026-10-25-qa-preview-design.md`

## Global Constraints

- Keep project operations under the shared lock and protect existing artwork and output files.
- Use temporary projects and synthetic images in tests.
- Run the Python suite and both required Node suites before committing.

## Review Focus

- Reject ambiguous selectors and missing or escaping processed references before output appears.
- Keep repeated playback slots and their durations, even when image bytes repeat.
- Paginate long contact sheets to keep images practical to view.
- Never replace an existing destination or write to formal art directories.
- Report the saved project revision and hashes of used frame files.

### Task 1: Read-only QA artifact renderer

**Files:** Create `tools/sprite_pipeline/qa.py`; create `tests/test_qa.py`.

- [x] Write tests for action and Review playback, repeated raw refs, contact pagination, timing, safety and failure cleanup.
- [x] Run tests and confirm failures from the missing feature.
- [x] Implement `render_qa(cfg, *, action, review, references, mode, output) -> dict` using existing playback expansion.
- [x] Run focused tests until green.

### Task 2: Agent CLI and documentation

**Files:** Modify `tools/sprite_pipeline/projects_cli.py`, `workspaces/README.md`, `docs/workbench.md`; extend `tests/test_qa.py`.

- [x] Add a failing CLI test for `projects.py qa` and its selector validation.
- [x] Implement CLI arguments and invoke the renderer under the project lock.
- [x] Document command examples and artifact meanings.
- [x] Run focused and full required tests, inspect output on a temporary project, then commit exact files.
