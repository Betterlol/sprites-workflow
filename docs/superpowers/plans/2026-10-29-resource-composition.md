# Unified resource composition

User authorized implementation of the first two proposed steps, with multiple commits and no actual tests. Do not run Python/Node/browser tests or operate existing artwork. Static syntax/lint and source review only; user performs runtime acceptance.

## Scope

- Keep v2 storage and existing action/review collections. Add `slots` as an optional canonical composition representation, without .meta migration.
- A slot has a stable local `id`, `resource: {kind: sprite|action|sequence, ref}`, optional finite repeat/range/speed, sprite duration, and referenced playback mode.
- Actions and sequences use the same resolver. Legacy sprites/clips are adapted in memory; no automatic project rewrite.
- References expand once by default, regardless of child loop flags. Reject missing resources, cycles, invalid ranges and excessive depth/size.
- Actions expose runtime/display projections of their compiled frames. Slot playback can explicitly select the referenced resource's display projection; duration otherwise inherits the child.
- Preserve leaf and slot provenance; apply dependency protection to sequence-only frames as well as actions.
- Unified library supports all types and inserts any type into either editor; collapsed slots can be expanded and their source resource opened.
- Preserve old display ordering when slots are edited by remapping occurrence origins; edits to a reference do not mutate its source.

## Commits

1. Domain graph and backend integration: resolver, validation, references, exports/QA/batch selection.
2. Shared browser graph model and unified library/timeline/editor.
3. Source review, integration corrections and documentation, if needed.

## Validation boundary

No actual test execution per user request. Report this explicitly at delivery. Keep existing project assets, untracked workspaces and shared pipeline.json files untouched.
