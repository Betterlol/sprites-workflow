# Sprite Workbench Interface Stage

**Goal:** Make the existing local editor readable, adjustable, and usable on narrow screens while making draft, preview, and stale material states explicit.

**Approved scope:** Stage 3 of `../specs/2026-10-25-workbench-improvements-design.md`. The earlier performance and workflow stages are complete. No artwork or `assets/` changes.

## Design direction

- Keep the charcoal work surface and restrained lime action color. Use clearer graphite layers (`#121419`, `#191c23`, `#242a34`), readable text (`#edf0f5`, `#b4becb`), lime (`#b8e77d`) for active editing, amber (`#e9ba79`) for pending work, and red (`#ef9292`) for failures. The canvas and sprite art remain the visual focus.
- Raise the UI's base type to 14 px. Form text and common controls stay at least 12 px; section labels and status text stay at least 11 px. Use the existing system sans stack for Chinese/English, and monospaced numerals only for frame/time data.
- Desktop: `[materials] | [canvas over transport and timeline] | [inspector]`, with keyboard and pointer adjustable column widths and timeline height. Keep controls aligned to each panel's own edge. A slim, labeled state rail sits between work modes and the editor.
- Narrow screens: show one work area at a time with visible Materials / Canvas / Properties buttons. The current work mode remains independent of the work area. Keep the canvas full width, make each area scroll on its own, and avoid page-wide horizontal scrolling.
- No new fonts, icon libraries, runtime dependencies, CSS animation system, or build step. Existing symbols may remain; status meaning must be written in text and never rely on color alone.

## Tasks

### 1. Readability and state rail

**Files:** `web/index.html`, `web/style.css`, `web/app.js`, `tests/test_workbench_session.mjs`, `docs/workbench.md`.

- Add three compact state messages: config draft, source preview, and processed material freshness. Derive preview state from the selected source recipe and saved data; refresh material metadata after Save so stale labels are accurate.
- Increase type/control sizes, spacing, focus visibility, panel headings, and contrast without covering the artwork. Preserve existing dark identity and fixed-canvas rendering.
- First write a failing session test for transitions between saved, draft, preview-pending, and stale material states. Run it red, implement, run all required suites, inspect desktop browser, then commit.

### 2. Adjustable desktop work areas

**Files:** `web/layout.js` (new), `web/index.html`, `web/style.css`, `web/app.js`, `tests/test_workbench_model.mjs`, `tests/test_workbench_session.mjs`, docs.

- Use two vertical separators and one horizontal separator. Pointer drag and arrow-key adjustment use the same clamped geometry; update ARIA values and persist sizes locally. Keep a minimum canvas width and minimum timeline/canvas heights. Ignore malformed saved sizes.
- Write failing geometry and keyboard/session tests first. Run red, implement, run all required suites, inspect desktop pointer behavior, then commit.

### 3. Narrow work-area navigation

**Files:** `web/index.html`, `web/style.css`, `web/app.js`, `tests/test_workbench_session.mjs`, docs.

- At 1100 px and below, present Materials / Canvas / Properties work-area buttons and render exactly one panel at a time. Selecting an item in Materials moves to Canvas; the user can always move back. The work-mode tabs remain available.
- Add failing session tests for area state and selection handoff. Run red, implement, run all required suites, inspect 375 px portrait and short landscape browser layouts, then commit.

### 4. Final review

- Review the entire stage against the approved spec with fresh context, fix Important findings with regression tests, and run all three required suites.
- Confirm real project can be opened without writing to its images; verify desktop and narrow layout in browser.
- Report commits, tests, and practical limitations. Leave the checkout and unrelated user files in place for testing.

## Review focus

- Draft status must not claim saved while unsaved config exists; preview status must not imply pixels were applied.
- After Save, a stale processed source must be labeled stale without forcing a rebuild.
- Resizing must never shrink the canvas below usable width, trap keyboard focus, or load a corrupt size from local storage.
- Narrow mode must not hide all three work areas or disconnect material selection from the canvas.
- Opening and browsing the real project must not create, delete, or regenerate artwork.

**Verification before each code commit:** `python -m unittest discover -s tests -v`, `node tests/test_workbench_model.mjs`, `node tests/test_workbench_session.mjs`, and `git diff --check`.
