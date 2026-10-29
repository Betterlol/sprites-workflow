# Sprite Workbench development

## Task routing

Start with the [Agent entry](docs/agents/README.md) and choose the reading path for the current task. Human UI instructions live in [users](docs/users/workbench.md); shared data and CLI contracts live in [reference](docs/reference/pipeline.md) and [project operations](docs/reference/project-operations.md); code responsibilities live in [development](docs/development/architecture.md). Historical plans and screenshots are not current specifications.

- Artwork creation, extension or repair: follow the mandatory artwork workflow below and the target project's own records.
- Code changes: read the [development Agent guide](docs/agents/development.md) and [contributing guide](docs/development/contributing.md); use temporary projects and synthetic assets.
- Documentation-only work: read the [documentation responsibility map](docs/README.md); check links and the diff, without running artwork operations or software/browser tests.
- Read-only inspection: use [project operations](docs/reference/project-operations.md), record the inspected versions, and do not turn inspection into mutation or visual approval.

The user's current scope and testing instructions take precedence. If the user will test the webpage, do not run browser tests yourself; report pending user checks. Reuse existing approvals and authorization.

## Shared assets and artwork gates

- Before artwork work, read `workspaces/README.md`, the mandatory [Agent sprite workflow](docs/agents/artwork-workflow.md), the target project's `README.md` and `pipeline.json`, then inspect its current state with `tools/projects.py status`. Follow the workflow's completion gates; reconcile stale documentation against actual references before generating.
- Use `tools/projects.py` for project creation, inspection, config saves, imports, processing and exports. It shares the browser's domain operations, revisions and process locks.
- Treat `pipeline.json`, source images, processed sprites and reference material as shared human/agent work. Preserve existing files and unsaved-work conflict protection.
- Keep `references/` selective: user references, one approved idle key pose and necessary final records only. Bind the exact idle path/version, source provenance, playable processed reference (if applicable), body proportions, visual scale, palette and ground anchor in the project README. Actually supply the idle image to later generations, alongside boundary images where needed; filenames in a prompt are insufficient. Reuse existing approvals and task authorization. If the idle image is playable, import its accepted original into `source/` as well. Legacy `reference/` remains readable and included in backups; references do not participate in extraction.
- Keep drafts, generated variants and other working files in an agent-owned task directory outside `references/`, `source/` and `processed_sprites/`, such as `workspaces/<project-id>/_work/<task>/`; follow the [work directory guide](docs/agents/work-directory.md) and use shared QA/check tools for repeatable evidence. Once artwork is selected, import the accepted original into `source/` before extraction and processing, including a single-frame correction. Keep processed results in their source-derived directories; treat `processed_sprites/imports/` and `_approved/` as existing compatibility or archival material, not the routine path for new artwork.
- Generate or extend animations as coherent spritesheets. Use a separate source sheet for each semantic subaction, keep each independently playable, and assemble the complete action from the same processed references. Animated idle also requires a sheet. Record runtime FPS, selected ranges, repetitions, shared-boundary removal and intentional holds.
- Resolve every handoff to exact runtime action slots and processed references, including the actual idle exit/return slots; never infer endpoints from source grid order, highest filenames or display playback. New subaction sheets start from the preceding approved endpoint. Directly share it only if pose, motion and state are continuous; play the shared boundary once unless a hold is documented.
- When direct continuity fails, actually provide both approved endpoints plus idle and nearby motion context to generate one whole transition spritesheet. Keep original endpoints in the assembled sequence and select reviewed interior transition frames; inspect both joins after processing. Matching endpoint poses alone does not establish natural motion. Single-frame generation is only for a specific faulty-frame repair, imported into `source/` before processing, never for assembling a transition from scattered frames.
- Check body scale and landmarks across sheets against idle. `fit_height` fits each source's complete silhouette, not a shared body scale; silhouette anchoring does not identify feet or preserve airborne displacement automatically. Record justified scale/offset corrections rather than equalizing every frame's height.
- Review each subaction, every handoff and the final sequence at runtime speed, slow playback and frame by frame. Check body scale, ground contact, motion direction/speed, expression and prop state. Local reviews must use the same endpoints and timing as the final action. Compare the expanded subaction composition with the complete action's references and durations; never omit a transition silently.
- Keep baseline, source/endpoint provenance, selection decisions, review evidence, inspected revisions and pass/pending results in the project README using the workflow template. Changes to images, processing or playback invalidate affected reviews. Config validation, software tests and exporting a WebP are not visual acceptance. Do not claim completion without actually inspecting the required playback; report pending checks explicitly. Archive superseded work before removing it from active use; do not renumber reusable sprites to change action order.
- Use repeated `--file` for imports and repeated `--ref` for deletions; deletion rejects assets still used by actions or sequences.
- Do not migrate, regenerate, delete or reorganize the existing `assets/` unless the user explicitly asks. Tests use temporary projects and synthetic images.
- Documentation-only tasks must not modify existing artwork or `pipeline.json`, or reprocess project images.

## Code validation

- For code changes, unless the user has explicitly restricted testing, validate with `python -m unittest discover -s tests -v`, `node tests/test_workbench_model.mjs` and `node tests/test_workbench_session.mjs`. Browser startup uses `python tools/serve_sprites.py`; no frontend build is required.

- Documentation-only changes require static link and change-scope checks, not the code test suites above. Commands and evidence boundaries are maintained in the [contributing guide](docs/development/contributing.md).
