"""Validated asset import, deletion and explicit legacy migration."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from sprite_pipeline.application.session import ProjectSession
from sprite_pipeline.domain.actions import action_steps, validate_editor
from sprite_pipeline.domain.resources import sprite_users
from sprite_pipeline.imaging.png import png_bytes
from sprite_pipeline.storage.configuration import IMAGE_SUFFIXES, inside
from sprite_pipeline.storage.files import numbered_frames, read_image, write_json
from sprite_pipeline.storage.history import OperationNotStarted


class AssetOperations:
    def __init__(self, session: ProjectSession) -> None:
        self.session = session

    def migrate(self, data: dict, revision: str, asset_revision: str | None = None) -> dict:
        """Preserve published/manual frame pixels as reusable approved assets."""
        with self.session.lock:
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            cfg = self.session.draft(data)
            copies = []
            changed = 0
            for name in cfg.data["actions"]:
                try:
                    final = numbered_frames(cfg.directory("sprites") / name, name)
                except FileNotFoundError:
                    continue
                refs = (
                    [step["ref"] for step in action_steps(cfg, name)]
                    if (cfg.action(name).get("sprites") or cfg.action(name).get("slots"))
                    else []
                )
                references = []
                for index, path in enumerate(final):
                    image = read_image(path)
                    if image.size != cfg.size:
                        raise ValueError(
                            f"{path.name}: final frame size does not match this project"
                        )
                    reference = refs[index] if index < len(refs) else None
                    processed = (
                        inside(cfg.directory("processed_sprites"), reference) if reference else None
                    )
                    if (
                        processed
                        and processed.exists()
                        and read_image(processed).tobytes() == image.tobytes()
                    ):
                        references.append(reference)
                    else:
                        digest = hashlib.sha256(image.tobytes()).hexdigest()[:12]
                        reference = f"_approved/{name}/{index:03d}-{digest}.png"
                        copies.append((path, inside(cfg.directory("processed_sprites"), reference)))
                        references.append(reference)
                        changed += 1
                cfg.data["actions"][name].pop("slots", None)
                cfg.data["actions"][name]["sprites"] = references
            validate_editor(cfg)
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            with self.session.history_transaction(
                "migrate", [self.session.path, *(destination for _, destination in copies)]
            ):
                for source, destination in copies:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                self.session.configs.save(cfg.data)
            return {**self.session.state(), "imported": changed}

    def upload(
        self,
        kind: str,
        filename: str,
        content: bytes,
        data: dict,
        revision: str,
        asset_revision: str | None = None,
    ) -> dict:
        with self.session.lock:
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            cfg = self.session.draft(data)
            if (
                not filename
                or Path(filename).name != filename
                or any(c in filename for c in '\\/:*?"<>|\x00')
                or filename.endswith((" ", "."))
            ):
                raise ValueError("Use an image filename without directory components")
            if Path(filename).suffix.lower() not in IMAGE_SUFFIXES:
                raise ValueError("Unsupported image format")
            with Image.open(io.BytesIO(content)) as original:
                original.load()
                image = original.convert("RGBA")
            if kind == "source":
                destination = inside(cfg.source, filename)
                stem = Path(filename).with_suffix("").as_posix().casefold()
                if stem in {"imports", "_approved"}:
                    raise ValueError("This filename is reserved for imported or approved sprites")
                if any(
                    cfg.source_id(name).casefold() == stem
                    for name in cfg.discover_sources(allow_empty=True, allow_missing=True)
                ):
                    raise ValueError("An original with this output name already exists")
                cfg.data.setdefault("sources", {}).setdefault(filename, {})
            elif kind == "processed":
                if image.size != cfg.size:
                    raise ValueError(f"Processed sprite must use the project canvas {cfg.size}")
                destination = inside(
                    cfg.directory("processed_sprites"), "imports/" + Path(filename).stem + ".png"
                )
                content = png_bytes(image)
            elif kind == "reference":
                destination = inside(self.session.reference_root(), filename)
            else:
                raise ValueError("Unknown upload category")
            if destination.exists():
                raise ValueError("An image with this filename already exists; rename the import")
            validate_editor(cfg)
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            with self.session.history_transaction(
                "upload " + kind, [self.session.path, destination]
            ):
                destination.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation also avoids races with external import tools.
                try:
                    output = destination.open("xb")
                except FileExistsError as error:
                    raise OperationNotStarted(
                        "An image with this filename already exists; rename the import"
                    ) from error
                with output:
                    output.write(content)
                self.session.configs.save(cfg.data)
            return self.session.state()

    def delete(
        self,
        kind: str,
        references: list[str],
        data: dict,
        revision: str,
        asset_revision: str | None = None,
    ) -> dict:
        """Delete a validated batch; in-use sprites and partial failures are protected."""
        with self.session.lock:
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            cfg = self.session.draft(data)
            validate_editor(cfg)
            if (
                not isinstance(references, list)
                or not 1 <= len(references) <= 1000
                or any(not isinstance(ref, str) for ref in references)
                or len({ref.casefold() for ref in references}) != len(references)
            ):
                raise ValueError("Select 1–1000 distinct image references")
            targets = []
            blocked_refs = set()
            prefixes = []
            metadata = {}

            def target_path(root: Path, reference: str) -> Path:
                path = inside(root, reference)
                if path != (root / reference).absolute():
                    raise ValueError(
                        "Linked paths cannot be deleted automatically; remove the link separately"
                    )
                return path

            if kind == "source":
                known = set(cfg.discover_sources(allow_empty=True, allow_missing=True)) | set(
                    cfg.data.get("sources", {})
                )
                for ref in references:
                    if ref not in known:
                        raise FileNotFoundError(f"Unknown source: {ref}")
                    source = target_path(cfg.source, ref)
                    if source.exists():
                        if not source.is_file():
                            raise ValueError(f"Source is not an image file: {ref}")
                        targets.append(source)
                    prefix = cfg.source_id(ref)
                    if any(
                        name != ref
                        and cfg.source_id(name).casefold().startswith(prefix.casefold() + "/")
                        for name in known
                    ):
                        raise ValueError(
                            "Source output directories overlap; fix the source rules before deletion"
                        )
                    prefixes.append(prefix + "/")
                    for stage in ("source_sprites", "processed_sprites"):
                        root = cfg.directory(stage)
                        directory = target_path(root, prefix)
                        if directory.exists():
                            # Resolve every descendant before moving a directory;
                            # a junction must never turn deletion into an escape.
                            for path in directory.rglob("*"):
                                inside(root, path.relative_to(root).as_posix())
                            targets.append(directory)
                    cfg.data.get("sources", {}).pop(ref, None)
            elif kind == "processed":
                blocked_refs.update(references)
                for ref in references:
                    path = self.session.image_path(kind, ref)
                    target_path(cfg.directory("processed_sprites"), ref)
                    if path.suffix.lower() != ".png":
                        raise ValueError("Processed references must be PNG files")
                    targets.append(path)
                    stage = target_path(
                        cfg.directory("processed_sprites"), str(Path(ref).parent / "_stage.json")
                    )
                    if stage.is_file():
                        payload = metadata.setdefault(
                            stage, json.loads(stage.read_text(encoding="utf-8"))
                        )
                        payload["files"] = [
                            name for name in payload.get("files", []) if name != path.name
                        ]
                        # Retain region identities and overrides: explicitly
                        # applying the source later may regenerate this sprite.
            elif kind == "reference":
                targets = [self.session.image_path(kind, ref) for ref in references]
                for ref in references:
                    target_path(self.session.path.parent, ref)
            else:
                raise ValueError("Unknown deletion category")
            uses = {
                name
                for ref, owners in sprite_users(cfg.data).items()
                for name in owners
                if ref in blocked_refs or any(ref.startswith(prefix) for prefix in prefixes)
            }
            if uses:
                raise ValueError(
                    "素材仍被动作使用，请先从这些动作移除或替换引用：" + ", ".join(sorted(uses))
                )
            self.session.check_revision(revision)
            self.session.check_assets(asset_revision)
            replacements = {**metadata, self.session.path: cfg.data}
            # Stage removed files and old metadata beside the project. If a
            # filesystem write fails, put them all back before reporting failure.
            with self.session.history_transaction("delete " + kind, [*targets, *replacements]):
                with TemporaryDirectory(
                    prefix=".sprite-delete-", dir=self.session.path.parent
                ) as temporary:
                    staged = []
                    written = []
                    try:
                        for index, path in enumerate(dict.fromkeys([*targets, *replacements])):
                            backup = Path(temporary) / str(index)
                            path.replace(backup)
                            staged.append((path, backup))
                        for path, payload in replacements.items():
                            if path == self.session.path:
                                self.session.configs.save(payload)
                            else:
                                write_json(path, payload)
                            written.append(path)
                    except BaseException:
                        for path in reversed(written):
                            path.unlink()
                        for path, backup in reversed(staged):
                            backup.replace(path)
                        raise
            return {**self.session.state(), "deleted": len(references)}
