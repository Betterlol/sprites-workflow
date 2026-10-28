"""Structural boundary for project queries, without depending on operations."""

from pathlib import Path
from typing import Protocol

from sprite_pipeline.storage.configuration import Config, ConfigRepository
from sprite_pipeline.storage.locking import ProjectLock

AssetMetadata = tuple[tuple[int, int], list[int], tuple[int, int, int, int] | None]


class QueryContext(Protocol):
    configs: ConfigRepository
    lock: ProjectLock
    path: Path
    project_id: str | None
    _asset_metadata: dict[Path, AssetMetadata]

    def validate_source_location(self, cfg: Config) -> None: ...
    def reference_root(self, name: str = "references") -> Path: ...
    def asset_revision(self, cfg: Config) -> str: ...
