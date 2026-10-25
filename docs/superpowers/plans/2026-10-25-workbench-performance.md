# Sprite Workbench Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce project opening, image browsing and source preview stalls while retaining existing safety checks.

**Architecture:** Reuse validated project state for unchanged image requests, keep versioned assets browser cacheable, and cache image metadata by file signature. Make preview responses smaller and reuse them by source and recipe; defer or limit background work in the client.

**Tech Stack:** Python 3.10+, FastAPI, Pillow, native JavaScript modules, Canvas 2D.

**Spec:** `docs/superpowers/specs/2026-10-25-workbench-improvements-design.md`

## Global Constraints

- Existing art is shared human/agent data and must not be rewritten by tests or setup.
- Browser and CLI retain config and asset revision protection; image paths remain contained in their validated stage roots.
- No frontend build or new dependency.
- Run `python -m unittest discover -s tests -v`, `node tests/test_workbench_model.mjs` and `node tests/test_workbench_session.mjs` before each stage completion claim.

## Review Focus

- A stale versioned image URL after file replacement must not cache new bytes under the old URL.
- A config path edit must invalidate image path state while traversal remains rejected.
- A processed PNG changed outside the workbench must refresh its bbox on the next snapshot.
- A preview after rapid source edits must display only the latest recipe.
- Repeated project checks must still find external changes before writes.

---

### Task 1: Versioned image delivery

**Files:** `tools/sprite_pipeline/projects.py`, `tools/sprite_pipeline/workbench.py`, `tools/sprite_pipeline/server.py`, `tests/test_projects.py`, `tests/test_workbench.py`

**Interfaces:** `ProjectStore.image_project(project_id) -> Project` obtains an existing validated project without revalidating every unchanged image request. `Project.image_path(kind, reference) -> Path` caches validated roots while the config file signature is unchanged. Image HTTP responses are immutable only when `v` matches the current file signature.

- [ ] Add HTTP tests for repeated valid URLs, changed content, stale versions, modified config paths and traversal.
- [ ] Run focused tests and observe the expected failure.
- [ ] Implement project/image path reuse and response cache headers.
- [ ] Run focused tests, the full three-suite gate, inspect diff, then commit `perf: cache validated image delivery`.

### Task 2: Snapshot metadata reuse

**Files:** `tools/sprite_pipeline/workbench.py`, `tests/test_projects.py`

**Interfaces:** `Project.state() -> dict` keeps its response shape and caches size/bbox for processed files keyed by path, nanosecond mtime and size. Missing or modified files invalidate entries.

- [ ] Add a test proving a repeated snapshot avoids decoding unchanged processed images and recomputes changed pixels.
- [ ] Run focused test and observe the expected failure.
- [ ] Implement metadata reuse without writing cache files into project data.
- [ ] Run focused tests, the full three-suite gate, inspect diff, then commit `perf: reuse sprite metadata in snapshots`.

### Task 3: Preview and browser work

**Files:** `tools/sprite_pipeline/workbench.py`, `tools/sprite_pipeline/web/app.js`, `tools/sprite_pipeline/web/player.js`, `tests/test_workbench.py`, `tests/test_workbench_session.mjs`

**Interfaces:** Preview JSON retains frame IDs, boxes, processed URLs and bbox, omits unused raw image URLs. Client preview requests are deduplicated by source plus draft rules and use epoch handling. Background polling pauses while hidden or busy and runs on focus with a longer idle interval. Playback preloads a bounded lookahead instead of every unique pose in a long sequence.

- [ ] Add failing Python and JavaScript tests for preview shape, stale-result handling and bounded preloading.
- [ ] Run focused tests and observe the expected failures.
- [ ] Implement response and client changes.
- [ ] Run focused tests, the full three-suite gate, inspect diff, then commit `perf: reduce preview and background loading`.

### Task 4: Real-project read-only benchmark

**Files:** No production files; record numbers in the final report.

- [ ] Benchmark only read-only requests against `workspaces/dafeiyu/` if present; do not process or export it.
- [ ] Compare cold and warm snapshot, repeated images, and preview payload size.
- [ ] Report any remaining bottleneck and let the user test this stage before the work on recovery, collaboration and UI.
