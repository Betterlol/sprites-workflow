"""Read-only project snapshots and cached asset metadata."""

from __future__ import annotations

import json

from PIL import Image

from sprite_pipeline.application.contracts import QueryContext
from sprite_pipeline.application.presentation import image_url
from sprite_pipeline.storage.configuration import IMAGE_SUFFIXES, inside, source_fingerprint

REFERENCE_DIRS = ("references", "reference")


def project_state(session: QueryContext) -> dict:
    with session.lock:
        snapshot = session.configs.snapshot()
        cfg = snapshot.config
        session.validate_source_location(cfg)
        assets = []
        root = cfg.directory("processed_sprites")
        present_assets = set()
        for path in sorted(root.rglob("*.png")):
            reference = path.relative_to(root).as_posix()
            inside(root, reference)
            present_assets.add(path)
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            cached = session._asset_metadata.get(path)
            if cached is None or cached[0] != signature:
                with Image.open(path) as image:
                    cached = (signature, list(image.size), image.convert("RGBA").getbbox())
                session._asset_metadata[path] = cached
            assets.append(
                {
                    "ref": reference,
                    "url": image_url("processed", reference, path, session.project_id),
                    "size": cached[1],
                    "bbox": cached[2],
                }
            )
        session._asset_metadata = {
            path: metadata
            for path, metadata in session._asset_metadata.items()
            if path in present_assets
        }
        sources = []
        discovered = cfg.discover_sources(allow_empty=True, allow_missing=True)
        for filename in discovered:
            path = inside(cfg.source, filename)
            with Image.open(path) as image:
                size = list(image.size)
            directory = inside(root, cfg.source_id(filename))
            stage_path = directory / "_stage.json"
            stage = (
                json.loads(stage_path.read_text(encoding="utf-8")) if stage_path.exists() else {}
            )
            fingerprint = stage.get("fingerprint")
            sources.append(
                {
                    "file": filename,
                    "url": image_url("source", filename, path, session.project_id),
                    "size": size,
                    "count": sum(
                        a["ref"].startswith(cfg.source_id(filename) + "/") for a in assets
                    ),
                    "stale": bool(fingerprint and fingerprint != source_fingerprint(cfg, filename)),
                }
            )
        legacy_count = len(list(cfg.directory("sprites").rglob("*.png")))
        reference_images = []
        for name in REFERENCE_DIRS:
            root = session.reference_root(name)
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                    relative = path.relative_to(root).as_posix()
                    inside(root, relative)
                    ref = name + "/" + relative
                    with Image.open(path) as image:
                        reference_images.append(
                            {
                                "ref": ref,
                                "file": relative,
                                "size": list(image.size),
                                "url": image_url("reference", ref, path, session.project_id),
                            }
                        )
        warnings = []
        missing = set(cfg.data.get("sources", {})) - set(discovered)
        if missing:
            warnings.append("原图缺失，请恢复图片或移除对应规则：" + ", ".join(sorted(missing)))
        references = {a["ref"] for a in assets}
        missing_refs = {
            ref
            for name in cfg.data["actions"]
            for ref in cfg.action(name).get("sprites") or []
            if ref not in references
        }
        if missing_refs:
            warnings.append(f"有 {len(missing_refs)} 个动作素材引用缺失，请准备素材或调整引用。")
        return {
            "data": cfg.data,
            "revision": snapshot.revision,
            "sources": sources,
            "assets": assets,
            "references": reference_images,
            "asset_revision": session.asset_revision(cfg),
            "warnings": warnings,
            "project_file": session.path.name,
            "legacy_count": legacy_count,
        }
