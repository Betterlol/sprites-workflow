# Sprite QA preview design

The user wants agents to stop writing task-specific browser capture scripts and saving hundreds of screenshots to inspect processed animation frames. Add one read-only CLI command to the existing project manager. It must use saved project state and the same action and Review playback expansion as the workbench.

The command accepts exactly one of an action, a saved Review, or an ordered list of processed sprite references. It writes a new output directory containing WebP and GIF previews, paginated contact sheets with every playback slot labeled, and JSON timing and provenance data. Raw references use the project's default FPS. Action playback can use runtime or display order; a Review uses its saved mode. The JSON timing data remains authoritative when an animated encoder merges identical pictures or rounds duration.

The output is disposable evidence, not a new source of truth. The command must not save project config, alter source or processed art, overwrite an existing destination, or place results in formal source, processed, or reference directories. It reads under the project lock and stages output before publishing it. Visual approval still requires a person or agent to inspect the actual animation; generated checks do not claim artistic quality.

Use existing Python and Pillow dependencies. Test with temporary projects and synthetic images only.
