# Agent Verification Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace repeated task-specific QA, composition and export verification scripts with narrow, reusable read-only CLI capabilities.

**Architecture:** Extend the existing QA renderer with an explicit sequence; add independent composition and export validators to the project manager. Use current playback expansion and saved processed frames as the source of truth.

**Tech Stack:** Python, Pillow, unittest, existing sprite pipeline.

**Spec:** `docs/superpowers/specs/2026-10-25-agent-verification-tools-design.md`

## Global Constraints

- No changes to user artwork, config or existing output files; all tests use temporary synthetic projects.
- Keep CLI reads under the shared project lock and return structured JSON.
- Run `python -m unittest discover -s tests -v` and both Node suites before completion.

## Review Focus

- Reject unsafe paths, ambiguous inputs and invalid sequence timing before publishing QA output.
- Preserve repeated slots and explicit authored durations even when encoders merge frames.
- Composition checks compare the runtime sequence exactly and distinguish an intentional hold from a shared boundary warning.
- Export checks must find a corrupted archive or wrong frame/atlas/preview, not merely regenerate the same export.
- State clearly when an old ZIP differs from current project assets or a format cannot retain exact authored colors/timing.

### Task 1: General sequence input for QA

**Files:** `tools/sprite_pipeline/qa.py`, `tools/sprite_pipeline/projects_cli.py`, `tests/test_qa.py`, `workspaces/README.md`, `docs/workbench.md`.

- [x] Write a failing test for explicit per-step durations, loop and invalid sequence input.
- [x] Implement `--sequence` as an alternative QA selector and keep existing selectors.
- [x] Run focused tests, document the JSON schema, and commit.

### Task 2: Exact composition check

**Files:** `tools/sprite_pipeline/composition_check.py`, `tools/sprite_pipeline/projects_cli.py`, `tests/test_composition_check.py`, `workspaces/README.md`.

- [x] Write failing tests for matching and mismatching action/Review sequences and explicit sequence input.
- [x] Implement a read-only JSON check with the first mismatching slot and boundary context.
- [x] Run focused tests, document usage, and commit.

### Task 3: Independent resource export check

**Files:** `tools/sprite_pipeline/export_check.py`, `tools/sprite_pipeline/projects_cli.py`, `tests/test_export_check.py`, `workspaces/README.md`.

- [ ] Write failing tests for a valid resource archive and corrupted frame, atlas and preview entries.
- [ ] Implement independent ZIP and pixel/timing validation against current processed PNGs.
- [ ] Run focused and required full suites, review final diff, and commit.
