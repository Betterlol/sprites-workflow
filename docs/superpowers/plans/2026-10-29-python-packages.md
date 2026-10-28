# Python responsibilities and package refactor

> Execution: use executing-plans inline; user authorized all three rounds and multiple commits.

**Goal:** Separate rules, image computation, application operations, storage and entry points without changing project formats or user workflows.

**Architecture:** Domain rules and imaging have no filesystem or transport dependency. Application services orchestrate storage and computation. HTTP and CLI share application operations; legacy module imports remain thin compatibility entry points.

**Tech stack:** Existing Python, Pillow, NumPy/SciPy, FastAPI and vanilla JavaScript; no new runtime framework.

**Spec:** The three-round proposal accepted in this conversation on 2026-10-29.

## Constraints and review focus

- Keep pipeline.json v2, assets and existing project layouts unchanged; defer .meta and configuration migration.
- Keep HTTP responses, CLI options, stable frame IDs, repeated/cross-source action timing and incremental pixel writes.
- Keep project locks, revisions, history rollback, cancellation and temporary export isolation.
- Preserve old import paths as explicit compatibility facades; internal code uses canonical packages.
- Tests use temporary projects and synthetic images. Browser validation is authorized for this task.
- Verify group-scale invalidation, extraction identity fallback, stale drafts, failed writes and legacy --config paths.

## Round 1: Rules and rendering

- [x] Add domain playback, validation, identity and result types; move pure image cutting/normalization into imaging.
- [x] Add application RenderService.render(config, source, stage) -> RenderResult; return versions with frames rather than mutable Project state.
- [x] Route QA/composition/export checks to domain action rules; retain public import compatibility.
- [x] Test independent render results, action timing and existing incremental/rollback behavior. Run all three required suites and commit.

## Round 2: Operations and storage

- [x] Move filesystem primitives/config IO/history/locks/slices into storage; centralize config reads/writes in ConfigRepository.
- [x] Split Project implementation into application session, query, editing, asset and export operations through composition, retaining a small facade.
- [x] Move HTTP/CLI entry points into interfaces; share application operations between HTTP and projects CLI. Preserve legacy batch CLI semantics through shared stage services.
- [x] Test entry point equivalence and transaction failure recovery; run all required suites and commit.

## Round 3: Quality and contracts

- [x] Tighten typed results/cache interfaces and explicit public exports; remove internal legacy imports and hidden side channels.
- [x] Add dependency-boundary/cycle checks, public import tests and architecture documentation describing future config adapter seam.
- [x] Run all required suites, browser smoke against a disposable synthetic project, and code review (independent service when available, otherwise inline review). Commit the final quality pass.

## Execution record

- Baseline: 0ce442e. Existing linked checkout is reused; user project files and screenshots remain outside commits.
- Existing behavior tests serve as refactor safety net; new tests cover newly explicit service contracts and architectural constraints.

- Round 1: 148 Python tests and both Node suites passed. An old tuple unpack in prepare was caught by existing job/rollback tests and changed to named RenderResult fields.

- Round 2: 149 Python tests and both Node suites passed. Project now composes session/editing/assets/export operations; configuration snapshots and saves use ConfigRepository. Legacy batch process still requires saved slices, while draft previews can render in memory. Both share pixel processing and slice storage.

- Round 3: 153 Python tests, both Node suites, architecture checks and Ruff check/format passed. Chromium smoke used a temporary project and passed slicing save, repeated/cross-source runtime/display timing, warm single-frame response deltas, unchanged neighboring PNG bytes/mtimes and reload.
- Review limitation: the independent review service returned HTTP 403 twice, so no independent review result is claimed. Inline review compared moved AST definitions and operation bodies against 0ce442e; filesystem/history/locking, CLI and export/QA algorithms remain equivalent, with intentional changes confined to delegation, config repository access, explicit render results and relocated static/default paths.
- Browser test corrections: wait for the initial preview to establish known versions before asserting a warm delta; assert successful save responses and actual files rather than matching a fragile toast substring. No product behavior was changed to satisfy these checks.
