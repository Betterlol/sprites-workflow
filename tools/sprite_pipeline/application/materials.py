"""Explain saved material freshness without rendering or changing project files."""

from __future__ import annotations

import json

from sprite_pipeline.storage.configuration import Config, inside, source_fingerprint

LABELS = {
    "synced": "已同步",
    "pending": "待更新",
    "unprocessed": "未处理",
    "unknown": "未核验",
}


def material_status(key: str, reason: str) -> dict:
    return {
        "key": key,
        "label": LABELS[key],
        "reason": reason,
        "pending": key in {"pending", "unprocessed"},
    }


def source_material_state(cfg: Config, filename: str, present_files: set[str]) -> dict:
    """Keep legacy ``stale`` semantics while reporting absent/unverified outputs.

    The existing digest includes source bytes and rules but stores no old inputs;
    a mismatch cannot truthfully identify which of them changed.
    ``present_files`` contains paths relative to this source's processed folder.
    """
    directory = inside(cfg.directory("processed_sprites"), cfg.source_id(filename))
    stage_path = directory / "_stage.json"
    try:
        stage = json.loads(stage_path.read_text(encoding="utf-8")) if stage_path.exists() else {}
        if not isinstance(stage, dict):
            raise ValueError("Invalid process inventory")
    except (OSError, ValueError):
        key = "unknown" if present_files else "unprocessed"
        reason = "处理记录无法读取，不能核验已有素材。" if present_files else "尚无处理后的素材帧。"
        return {"stale": False, "material_status": material_status(key, reason)}

    fingerprint = stage.get("fingerprint")
    stale = bool(fingerprint and fingerprint != source_fingerprint(cfg, filename))

    def result(key: str, reason: str) -> dict:
        return {"stale": stale, "material_status": material_status(key, reason)}

    files = stage.get("files")
    valid_files = (
        isinstance(files, list)
        and bool(files)
        and all(isinstance(name, str) and name.endswith(".png") for name in files)
    )
    if valid_files:
        missing = set(files) - present_files
        if missing:
            return result("pending", f"处理记录中的 {len(missing)} 个素材帧缺失，需重新应用。")
    if not present_files:
        return result("unprocessed", "尚无处理后的素材帧，请准备素材或应用原图处理。")
    if stage.get("source") != filename or stage.get("stage") != "process":
        return result("unknown", "缺少匹配的处理记录，不能核验已有素材。")
    if not valid_files:
        return result("unknown", "处理记录缺少有效帧清单，不能核验已有素材。")
    if not fingerprint:
        return result("unknown", "已有素材缺少处理版本记录，无法确认是否与当前原图和规则一致。")
    if stale:
        return result(
            "pending", "原图或已保存的切割、处理、画布规则与上次应用时不同；旧记录无法细分原因。"
        )
    return result("synced", "已有素材帧完整，处理记录与当前原图及已保存规则一致。")
