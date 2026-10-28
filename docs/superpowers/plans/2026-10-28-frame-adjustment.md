# Incremental frame adjustment

User approved second round after accepting slicing; first round committed as `36b7319`. Execute inline, use regression/unit tests only. Do not launch browser tests or proceed to the next round.

## Scope
- Cache processing by native pixels, effective per-frame recipe, resolved group scale, canvas and anchor. Changing one override normalizes only that frame. Bound caches by memory, preserve fit-height dependencies and error checks.
- Preview supports version-aware responses: unchanged image data omitted, old clients retain full responses. Browser merges by stable ref; stale requests cannot overwrite the selected source or draft.
- Applying updates writes only changed PNGs; unchanged PNG bytes and mtimes remain untouched. Preserve whole-draft apply semantics and conflict/history protection; no new config migration.
- Adjustment preview uses an explicitly selected action through the same actionSteps runtime/display calculation. Preserve repeated references and cross-source steps. Fallback to a clearly named source inspection mode when no action exists, using project FPS rather than fixed 100ms.
- Editing a different source via an action slot routes to its actual source, never applies an override to the wrong source. Imported-only frames remain playable but cannot use source processing controls.
- Keep edited selection separate from playback position. Refreshing pixels preserves elapsed playback, updates repeated occurrences together, and avoids rebuilding unchanged timeline cards.

## Implementation and validation
- [x] Regression tests: one-frame normalization/encoding, cache invalidation, unchanged file mtime, rollback; action order/durations, repeated/cross-source refs, delta merge and player continuity.
- [x] Backend bounded render cache, delta preview and incremental apply.
- [x] Frontend action context, targeted preview updates and source routing.
- [x] Run repository Python and both Node suites; fresh code review; documentation and server handoff. No browser testing.

## Completion record

- Accepted slicing work committed as 36b7319 before starting this round.
- Implemented bounded native/render/encoded caches, version-aware preview merging, targeted PNG writes with scoped history, and actual action-context adjustment (runtime/display, repeated and cross-source frames).
- Regression checks: 147 Python tests and both Node suites passed. New tests observe one normalize/encode operation for one override, no extraction repeat, unchanged neighboring PNG bytes/mtime, exact action order/durations, cross-source ownership and preserved playback progress.
- Fresh review found no actionable correctness defects. Follow-up regression checks also cover selecting the source-owned slot and retaining the exact repeated slot when locating a frame from an action.
- Per user instruction, no browser tests were run. Web interaction and visual acceptance remain for the user. No next-round work or artwork migration performed. Second-round changes remain uncommitted.
