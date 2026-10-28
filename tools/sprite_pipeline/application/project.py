"""Public application facade shared by HTTP, CLI and background jobs.

Each operation owns its existing lock/transaction scope; this facade only routes.
"""
from __future__ import annotations
from pathlib import Path
from sprite_pipeline.storage.configuration import Config, source_fingerprint
from sprite_pipeline.application.session import ProjectSession
from sprite_pipeline.application.editing import EditingOperations
from sprite_pipeline.application.assets import AssetOperations
from sprite_pipeline.application.exporting import ExportOperations

class Project:
    def __init__(self, path: Path, project_id: str | None = None):
        self.session = ProjectSession(path, project_id)
        self.editing = EditingOperations(self.session)
        self.assets = AssetOperations(self.session)
        self.exporting = ExportOperations(self.session)

    def history_transaction(self, operation: str, paths: list[Path]):
        return self.session.history_transaction(operation, paths)

    def history_entries(self):
        return self.session.history_entries()

    def restore(self, version_id: str, revision: str, asset_revision: str | None=None):
        return self.session.restore(version_id, revision, asset_revision)

    def config_signature(self):
        return self.session.config_signature()

    def validate_source_location(self, cfg: Config):
        return self.session.validate_source_location(cfg)

    @property
    def revision(self):
        return self.session.revision

    def check_revision(self, revision: str):
        return self.session.check_revision(revision)

    def asset_revision(self, cfg: Config):
        return self.session.asset_revision(cfg)

    def check_assets(self, revision: str | None):
        return self.session.check_assets(revision)

    def changes(self):
        return self.session.changes()

    def draft(self, data: dict):
        return self.session.draft(data)

    def image_path(self, kind: str, reference: str):
        return self.session.image_path(kind, reference)

    def reference_root(self, name: str='references'):
        return self.session.reference_root(name)

    def render(self, data: dict, filename: str, stage: str='process'):
        return self.session.render(data, filename, stage)

    def state(self):
        return self.session.state()

    def save(self, data: dict, revision: str):
        return self.editing.save(data, revision)

    def save_slices(self, filename: str, extract: dict, revision: str, asset_revision: str | None=None):
        return self.editing.save_slices(filename, extract, revision, asset_revision)

    def preview(self, data: dict, filename: str, stage: str='process', known: dict | None=None):
        return self.editing.preview(data, filename, stage, known)

    def apply(self, data: dict, revision: str, filename: str, asset_revision: str | None=None):
        return self.editing.apply(data, revision, filename, asset_revision)

    def prepare(self, data: dict, revision: str, asset_revision: str | None=None, *, progress=None, cancelled=None):
        return self.editing.prepare(data, revision, asset_revision, progress=progress, cancelled=cancelled)

    def migrate(self, data: dict, revision: str, asset_revision: str | None=None):
        return self.assets.migrate(data, revision, asset_revision)

    def upload(self, kind: str, filename: str, content: bytes, data: dict, revision: str, asset_revision: str | None=None):
        return self.assets.upload(kind, filename, content, data, revision, asset_revision)

    def delete(self, kind: str, references: list[str], data: dict, revision: str, asset_revision: str | None=None):
        return self.assets.delete(kind, references, data, revision, asset_revision)

    def export(self, data: dict, options: dict, *, progress=None, cancelled=None, expected_asset_revision: str | None=None, expected_revision: str | None=None):
        return self.exporting.export(data, options, progress=progress, cancelled=cancelled, expected_asset_revision=expected_asset_revision, expected_revision=expected_revision)

    @property
    def path(self):
        return self.session.path

    @property
    def project_id(self):
        return self.session.project_id

    @property
    def lock(self):
        return self.session.lock

    @property
    def versions(self):
        return self.session.versions

    @property
    def renderer(self):
        return self.session.renderer

    def fingerprint(self, cfg: Config, filename: str) -> str:
        return source_fingerprint(cfg, filename)
