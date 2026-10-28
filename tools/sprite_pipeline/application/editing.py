"""Draft editing, scoped slice saves and incremental frame application."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from sprite_pipeline.application.presentation import data_url
from sprite_pipeline.application.session import ProjectSession
from sprite_pipeline.domain.actions import validate_editor
from sprite_pipeline.domain.errors import OperationCancelled
from sprite_pipeline.domain.models import Cancellation, Progress
from sprite_pipeline.storage.configuration import inside, source_fingerprint
from sprite_pipeline.storage.files import frame_changes, replace_frames
from sprite_pipeline.storage.identities import previous_slices
from sprite_pipeline.storage.slices import write_slices


class EditingOperations:
    def __init__(self, session: ProjectSession) -> None:
        self.session = session

    def save(self, data: dict, revision: str) -> dict:
        with self.session.lock:
            self.session.check_revision(revision)
            cfg = self.session.draft(data)
            validate_editor(cfg)
            self.session.check_revision(revision)
            self.session.configs.save(cfg.data)
            return {"revision": self.session.revision}

    def save_slices(
        self, filename: str, extract: dict, revision: str, asset_revision: str | None = None
    ) -> dict:
        """Commit only one extraction recipe and its native slices, preserving other edits."""
        with self.session.lock:
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            current = self.session.configs.load()
            baseline_assets = self.session.asset_revision(current)
            data = copy.deepcopy(current.data)
            settings = data.setdefault("sources", {}).setdefault(filename, {})
            settings["extract"] = copy.deepcopy(extract)
            previous = previous_slices(current, filename)
            old_ids = {Path(item["file"]).stem for item in previous}
            minimum = max(
                current.source_spec(filename)["extract"].get("next_id", 0),
                max([int(key) for key in old_ids] + [-1]) + 1,
            )
            settings["extract"]["next_id"] = max(minimum, settings["extract"].get("next_id", 0))
            rendered = self.session.render(data, filename, "extract")
            cfg, images, descriptors = rendered.config, rendered.raw, rendered.descriptors
            keys = set(images)
            prefix = cfg.source_id(filename) + "/"
            available = {prefix + item["file"] for item in descriptors}
            broken = {
                ref
                for name in current.data["actions"]
                for ref in (current.action(name).get("sprites") or [])
                if ref.startswith(prefix) and ref not in available
            }
            if broken:
                raise ValueError(
                    "区域仍被已保存动作使用，请先保存动作中的移除或替换："
                    + ", ".join(sorted(broken))
                )
            unused_overrides = (
                set(current.source_spec(filename)["process"].get("overrides", {})) - keys
            )
            if unused_overrides:
                raise ValueError(
                    "区域仍有已保存的单帧调整，请先重置并保存这些帧："
                    + ", ".join(sorted(unused_overrides))
                )
            rules = cfg.data["sources"][filename]["extract"]
            rules["identities"] = descriptors
            rules["next_id"] = max(rules["next_id"], max(map(int, keys), default=-1) + 1)
            if rules.get("method") == "boxes":
                rules["region_ids"] = list(images)
            directory = inside(cfg.directory("source_sprites"), cfg.source_id(filename))
            self.session.check_revision(revision)
            self.session.check_assets(baseline_assets)
            with self.session.history_transaction("save slices", [self.session.path, directory]):
                write_slices(cfg, filename, images, descriptors)
                self.session.configs.save(cfg.data)
            return self.session.state()

    def preview(
        self, data: dict, filename: str, stage: str = "process", known: dict | None = None
    ) -> dict:
        with self.session.lock:
            if known is not None and (
                not isinstance(known, dict) or any(not isinstance(v, str) for v in known.values())
            ):
                raise ValueError("known must map frame references to preview versions")
            rendered = self.session.render(data, filename, stage)
            cfg, _raw, frames, descriptors, scale = (
                rendered.config,
                rendered.raw,
                rendered.frames,
                rendered.descriptors,
                rendered.scale,
            )
            result = []
            for item in descriptors:
                image = frames[item["file"]]
                version = (
                    rendered.versions.get(item["file"])
                    or hashlib.sha256(image.tobytes() + str(image.size).encode()).hexdigest()
                )
                ref = cfg.source_id(filename) + "/" + item["file"]
                frame = {
                    "id": Path(item["file"]).stem,
                    "ref": ref,
                    "box": item["source_box"],
                    "bbox": image.getbbox(),
                    "version": version,
                }
                if known is None or known.get(ref) != version:
                    url = self.session._encoded_cache.get(version)
                    if url is None:
                        url = data_url(image)
                        self.session._encoded_cache.put(version, url, len(url))
                    frame["url"] = url
                result.append(frame)
            return {
                "stage": stage,
                "scale": scale,
                "next_id": max(
                    cfg.source_spec(filename)["extract"].get("next_id", 0),
                    max(map(int, _raw), default=-1) + 1,
                ),
                "frames": result,
            }

    def apply(
        self, data: dict, revision: str, filename: str, asset_revision: str | None = None
    ) -> dict:
        with self.session.lock:
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            rendered = self.session.render(data, filename)
            cfg, frames, descriptors, scale = (
                rendered.config,
                rendered.frames,
                rendered.descriptors,
                rendered.scale,
            )
            validate_editor(cfg)
            prefix = cfg.source_id(filename) + "/"
            available = {prefix + name for name in frames}
            broken = {
                ref
                for name in cfg.data["actions"]
                for ref in (cfg.action(name).get("sprites") or [])
                if ref.startswith(prefix) and ref not in available
            }
            if broken:
                raise ValueError(
                    "切图会移除正在使用的素材，请先从动作中移除或替换这些引用："
                    + ", ".join(sorted(broken))
                )
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            cfg.data.setdefault("sources", {}).setdefault(filename, {}).setdefault("extract", {})[
                "identities"
            ] = descriptors
            directory = inside(cfg.directory("processed_sprites"), cfg.source_id(filename))
            changed, removed = frame_changes(directory, frames, r"\d+\.png")
            paths = (
                [directory]
                if not directory.exists()
                else [directory / "_stage.json", *[directory / name for name in changed], *removed]
            )
            with self.session.history_transaction("apply", [self.session.path, *paths]):
                replace_frames(
                    directory,
                    frames,
                    owned=r"\d+\.png",
                    metadata={
                        "stage": "process",
                        "source": filename,
                        "scale": scale,
                        "files": list(frames),
                        "frames": descriptors,
                        "fingerprint": source_fingerprint(cfg, filename),
                    },
                    write_names=changed,
                )
                self.session.configs.save(cfg.data)
            return self.session.state()

    def prepare(
        self,
        data: dict,
        revision: str,
        asset_revision: str | None = None,
        *,
        progress: Progress | None = None,
        cancelled: Cancellation | None = None,
    ) -> dict:
        """Prepare absent sources only; existing processed artwork is never rebuilt."""
        with self.session.lock:
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            cfg = self.session.draft(data)
            pending = []
            sources = cfg.discover_sources()
            if progress is not None:
                progress(0, len(sources), "准备原图")
            for index, filename in enumerate(sources, 1):
                if cancelled is not None and cancelled.is_set():
                    raise OperationCancelled("Preparation cancelled")
                directory = inside(cfg.directory("processed_sprites"), cfg.source_id(filename))
                if not list(directory.glob("*.png")):
                    rendered = self.session.render(cfg.data, filename)
                    pending.append((filename, rendered))
                if progress is not None:
                    progress(index, len(sources), filename)
                if cancelled is not None and cancelled.is_set():
                    raise OperationCancelled("Preparation cancelled")
            # Render all sources before making any changes on validation failure.
            validate_editor(cfg)
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            if cancelled is not None and cancelled.is_set():
                raise OperationCancelled("Preparation cancelled")
            directories = [
                inside(cfg.directory("processed_sprites"), cfg.source_id(filename))
                for filename, _ in pending
            ]
            with self.session.history_transaction("prepare", [self.session.path, *directories]):
                for filename, rendered in pending:
                    frames, descriptors, scale = (
                        rendered.frames,
                        rendered.descriptors,
                        rendered.scale,
                    )
                    cfg.data.setdefault("sources", {}).setdefault(filename, {}).setdefault(
                        "extract", {}
                    )["identities"] = descriptors
                    replace_frames(
                        inside(cfg.directory("processed_sprites"), cfg.source_id(filename)),
                        frames,
                        owned=r"\d+\.png",
                        metadata={
                            "stage": "process",
                            "source": filename,
                            "scale": scale,
                            "files": list(frames),
                            "frames": descriptors,
                            "fingerprint": source_fingerprint(cfg, filename),
                        },
                    )
                self.session.configs.save(cfg.data)
            return self.session.state()
