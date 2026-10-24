# Sprite Workbench development

- Project data lives in `workspaces/<project-id>/`; read `workspaces/README.md` before operating on artwork.
- Use `tools/projects.py` for project creation, inspection, config saves, imports, processing and exports. It shares the browser's domain operations, revisions and process locks.
- Treat `pipeline.json`, source images, processed sprites and reference material as shared human/agent work. Preserve existing files and unsaved-work conflict protection.
- Keep manual sprites in `processed_sprites/imports/` or `_approved/`. Do not renumber reusable sprites to change action order.
- Store reference material in `references/`; legacy `reference/` remains readable and is included in backups. References do not participate in extraction. Use repeated `--file` for imports and repeated `--ref` for deletions; deletion rejects assets still used by actions.
- Do not migrate, regenerate, delete or reorganize the existing `assets/` unless the user explicitly asks. Tests use temporary projects and synthetic images.
- Validate changes with `python -m unittest discover -s tests -v`, `node tests/test_workbench_model.mjs` and `node tests/test_workbench_session.mjs`. Browser startup uses `python tools/serve_sprites.py`; no frontend build is required.
