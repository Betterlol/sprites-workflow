# Frame offset drag preview implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Drag the selected image in source processing to preview its single-frame offset, synchronizing the offset fields before explicitly applying and saving.

**Architecture:** Keep the current preview as a baseline and translate its selected image locally during dragging. Commit one offset edit to the existing draft history on release, then request the existing authoritative processing preview. Pending translations belong to the current preview only; action playback and stored assets remain unchanged until application.

**Tech Stack:** Existing JavaScript modules, canvas, Pointer Events, Python workbench API.

**Spec:** User request in this chat; preserve the current application/save boundary and existing conflict protection.

## Global constraints

- Work only in the new `codex/frame-offset-preview` worktree.
- Preserve artwork, source files, processed sprites and project configuration.
- Keep numeric editing available as an alternative to dragging.
- Use temporary projects and synthetic images for browser verification.

## Review focus

- Canvas zoom converts screen movement to image pixels correctly.
- Consecutive drags accumulate before server previews return, including movement outside the canvas.
- Cancellation, stale requests, source switching and undo cannot transfer an offset to another image.
- Previous-frame and idle overlays stay fixed while the selected frame moves.
- Copy processing ignores offsets; do not advertise or simulate an edit that cannot be applied.

## Task 1: Drag preview and regression coverage

**Files:** `tools/sprite_pipeline/web/app.js`, `player.js`, `style.css`, `tests/test_workbench_session.mjs`, `tests/test_workbench_model.mjs`, `docs/workbench.md`.

- [x] Inspect current preview, processing, player and draft history contracts; create isolated worktree.
- [x] Reproduce baseline: Python 112 tests and model tests pass; session harness fails on CRLF import stripping. Fix its newline handling before feature tests.
- [x] Add failing session tests for zoom-aware drag, synchronized fields, one undo step, cancellation, accumulating pending offsets and explicit apply payload.
- [x] Add failing canvas tests for translated current image with fixed overlays.
- [x] Implement pointer capture, local preview translations, draft update on release and authoritative preview refresh; guard stale results and copy mode.
- [x] Update usage hints and document the interaction.
- [x] Run all required Python and Node suites and browser checks using synthetic sprites.
- [x] Review the final diff and record evidence; leave the worktree available for the user.

## Verification evidence (2026-10-25)

- `python -m unittest discover -s tests -v`: 112 tests passed.
- `node tests/test_workbench_model.mjs` and `node tests/test_workbench_session.mjs`: passed, including drag movement, fixed overlays, pending adjustments, cancellation, stale responses, copy mode, explicit apply and one-step undo.
- Additional session checks: secondary buttons, unrelated pointers, clicks without movement, lost capture, movement outside the canvas and switching away during a drag.
- Browser fixture: temporary `sprite-drag-preview-08r2af1g` project, synthetic 2-cell image, 256 × 256 canvas. No existing project artwork/configuration was used or changed.
- At 200%, a 40 × -20 screen-pixel drag changed the selected offset from `[0, 0]` to `[20, -10]`; the visible blue bounding box changed from `[116, 170, 140, 210]` to `[136, 160, 160, 200]` both during and after preview processing. Previous-frame/idle reference pixels remained at their original position.
- Before explicit application, SHA-256 comparisons confirmed `pipeline.json` and both processed PNGs were unchanged. After application, the selected processed PNG had exactly the previewed bounding box, while the first PNG remained byte-identical.
- Browser Escape cancellation and undo/redo restored the correct offsets. At 50%, a 31.5 screen-pixel drag added 64 image pixels after excluding the CSS border; undo restored the original value.
- At 390 × 844, dragging added `[8, -4]`, and the inspector showed the same offset after processing; no page horizontal overflow. Desktop and narrow screenshots were inspected.
- Independent review found a border-coordinate discrepancy; a failing regression test reproduced it, the conversion was corrected, and the reviewer reported no remaining actionable findings.
- `git diff --check`: clean. Worktree and branch retained separately from the original checkout; no merge or publish performed.
