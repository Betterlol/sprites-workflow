"""Resolve stable IDs against authored rules or legacy stage inventories."""
import json
from sprite_pipeline.storage.configuration import Config, inside
from sprite_pipeline.domain.identity import preserve_slice_ids

def previous_slices(cfg: Config, filename: str) -> list[dict]:
    authored = cfg.source_spec(filename)["extract"].get("identities")
    if authored:
        return authored
    # Older projects fall back to stage inventories until the first GUI apply.
    for stage in ("processed_sprites", "source_sprites"):
        inventory = inside(cfg.directory(stage), cfg.source_id(filename)) / "_stage.json"
        if inventory.exists():
            payload = json.loads(inventory.read_text(encoding="utf-8"))
            if payload.get("source") == filename and payload.get("frames"):
                return payload["frames"]
    return []

def slice_ids(cfg: Config, filename: str, boxes: list[tuple]) -> list[str]:
    spec = cfg.source_spec(filename)['extract']
    explicit = spec.get('region_ids') if spec.get('method') == 'boxes' else None
    if explicit is not None:
        if len(explicit) != len(boxes):
            raise ValueError('extract.region_ids must match extract.boxes')
        return list(explicit)
    return preserve_slice_ids(boxes, previous_slices(cfg, filename), spec.get('next_id', 0))
