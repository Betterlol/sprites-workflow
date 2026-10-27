# Independent slicing implementation plan

**Goal:** Complete the approved first round only: direct region editing, stable IDs, independent slicing save, reusable native slices.

**Execution:** Inline using writing-plans, executing-plans, test-driven-development and verification-before-completion. Existing branch/checkout retained. No artwork migration or automatic commits.

**Design decisions**
- Keep pipeline version 2. Manual boxes gain aligned `region_ids`; `next_id` is a monotonically increasing allocation watermark. Existing `identities` and legacy stage inventories remain readable.
- Save slicing through a shared Project operation and CLI command. Only the selected source's extraction specification and raw slice cache change. Processing pixels, actions and unrelated drafts are preserved.
- Persist native slices in existing `source_sprites/<source>/`, with source/extraction fingerprint and per-file checksums. Process/canvas edits do not invalidate extraction. Missing/stale/corrupt slices are rebuilt in memory for preview, and persisted only on explicit slicing save.
- Keep protected runtime references intact. Removing a slice referenced by saved actions or saved per-frame overrides fails with an actionable message. Web additionally checks unsaved action/override references.
- In the browser, scoped saving rebases the server snapshot underneath the remaining draft and retains applicable undo history without erasing the ID allocation watermark.
- Selection/move/resize and new-region tools are explicit. Pointer gestures only redraw the canvas until completion, support Escape/cancellation, and produce one undo step. Geometry and IDs are independent of preview responses.
- Stage save is a file/history transaction; existing conflict and rollback protections remain.

## Tasks and verification

- [x] Backend tests first: stable explicit IDs, deletion/reallocation, save isolation, reference protection, stale revisions, rollback, cache reuse and invalidation.
- [x] Shared extraction identity/cache helpers; independent save operation, HTTP and CLI adapters; process consumes verified slices.
- [x] Frontend geometry and session tests; selection/creation/move/resize, source-pixel coordinates, keyboard nudging, stable selection and scoped draft/save handling.
- [x] Browser checks on temporary synthetic projects: drag/resize, cancellation/undo, save/reload, unrelated unsaved drafts, action reference protection, cache reuse, narrow layout.
- [x] Run all three repository suites; fresh review; document behavior and start local test server.

## Boundaries

Per-frame incremental processing, action-context playback and physical metadata decomposition remain the next round. Existing user artwork and pipelines are not modified by development or tests.

## Completion record

- Implemented scoped extraction saves, stable manual IDs, verified native slice reuse, direct region gestures and CLI parity. No existing workspace artwork or pipelines were modified.
- Final automated checks: 143 Python tests and both Node suites passed. Browser checks performed before the user requested that browser testing stop. The user will handle further webpage acceptance; no additional browser testing or next-stage implementation is authorized in this round.
- Review findings on first-save identity handoff and empty manual fallback were fixed with regression coverage.
- Local server launched on port 8765 for user testing. Changes remain uncommitted.
