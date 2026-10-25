"""Resource ZIP verification against synthetic processed artwork."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.config import load_config
from sprite_pipeline.files import write_json
from sprite_pipeline.projects import ProjectStore
from sprite_pipeline.projects_cli import main as manage


class ExportCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspaces = self.root / "workspaces"
        self.store = ProjectStore(self.workspaces)
        self.store.create("Export", "fish", frame_size=[16, 16])
        cfg = load_config(self.workspaces / "fish/pipeline.json")
        folder = cfg.directory("processed_sprites") / "walk"
        folder.mkdir(parents=True)
        for index, color in enumerate(("red", "blue")):
            image = Image.new("RGBA", cfg.size, (0, 0, 0, 0))
            image.paste(color, (index * 6 + 1, 4, index * 6 + 5, 9))
            image.save(folder / f"{index:03d}.png")
        cfg.data["actions"]["walk"] = {
            "sprites": ["walk/000.png", "walk/001.png"], "fps": 10, "loop": False,
            "animation": {"order": [0, 1, 0], "durations_ms": [100, 120, 80], "loop": 1},
        }
        write_json(cfg.path, cfg.data)
        self.cfg = load_config(cfg.path)

    def export(self, kind="all"):
        content, _, _ = self.store.get("fish").export(
            self.cfg.data, {"format": kind, "actions": ["walk"]})
        path = self.root / f"fish-{kind}.zip"
        path.write_bytes(content)
        return path

    def replace(self, original, entry, content, name="tampered.zip"):
        output = self.root / name
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(output, "w") as target:
            for info in source.infolist():
                target.writestr(info, content if info.filename == entry else source.read(info))
        return output

    def inspect(self, archive):
        from sprite_pipeline.export_check import check_export
        return check_export(self.cfg, archive)

    def test_valid_all_and_webp_only_exports_check_without_mutation(self):
        before = self.cfg.path.read_bytes()
        complete = self.inspect(self.export("all"))
        self.assertTrue(complete["valid"], complete["issues"])
        self.assertEqual(complete["actions"][0]["name"], "walk")
        self.assertEqual(complete["actions"][0]["formats"], ["frames", "atlas", "webp", "gif"])
        self.assertTrue(self.inspect(self.export("webp"))["valid"])
        self.assertTrue(self.inspect(self.export("frames"))["valid"])
        self.assertEqual(self.cfg.path.read_bytes(), before)
        self.assertFalse((self.cfg.root / "exports").exists())

    def test_changed_frame_and_atlas_pixels_fail_independently(self):
        archive = self.export()
        wrong = io.BytesIO()
        Image.new("RGBA", self.cfg.size, "purple").save(wrong, "PNG")
        frame = self.replace(archive, "sprites/walk/walk_00.png", wrong.getvalue(), "wrong-frame.zip")
        report = self.inspect(frame)
        self.assertFalse(report["valid"])
        self.assertTrue(any("sprites/walk/walk_00.png" in issue["path"] for issue in report["issues"]))

        with zipfile.ZipFile(archive) as source:
            with Image.open(io.BytesIO(source.read("spritesheets/fish_walk.png"))) as image:
                sheet = image.convert("RGBA")
        sheet.putpixel((2, 5), (99, 99, 99, 255))
        buffer = io.BytesIO()
        sheet.save(buffer, "PNG")
        atlas = self.replace(archive, "spritesheets/fish_walk.png", buffer.getvalue(), "wrong-atlas.zip")
        report = self.inspect(atlas)
        self.assertFalse(report["valid"])
        self.assertTrue(any("spritesheets/fish_walk.png" in issue["path"] for issue in report["issues"]))

    def test_atlas_timing_and_manifest_are_verified(self):
        archive = self.export()
        with zipfile.ZipFile(archive) as source:
            atlas = json.loads(source.read("spritesheets/fish_walk.json"))
            manifest = json.loads(source.read("fish_manifest.json"))
        atlas["frames"]["walk_00.png"]["duration"] = 999
        changed_atlas = self.replace(archive, "spritesheets/fish_walk.json",
                                     json.dumps(atlas).encode(), "bad-atlas-timing.zip")
        report = self.inspect(changed_atlas)
        self.assertFalse(report["valid"])
        self.assertTrue(any(issue["path"] == "spritesheets/fish_walk.json" for issue in report["issues"]))

        atlas["frames"]["walk_00.png"]["duration"] = 100
        atlas["frames"]["walk_00.png"]["rotated"] = True
        rotated = self.replace(archive, "spritesheets/fish_walk.json",
                               json.dumps(atlas).encode(), "rotated-atlas.zip")
        self.assertFalse(self.inspect(rotated)["valid"])

        atlas["frames"]["walk_00.png"]["rotated"] = False
        atlas["frames"]["walk_00.png"]["spriteSourceSize"]["x"] = 99
        offset = self.replace(archive, "spritesheets/fish_walk.json",
                              json.dumps(atlas).encode(), "wrong-source-offset.zip")
        self.assertFalse(self.inspect(offset)["valid"])

        atlas["frames"]["walk_00.png"]["spriteSourceSize"]["x"] = 0
        atlas["meta"]["image"] = "missing.png"
        wrong_image = self.replace(archive, "spritesheets/fish_walk.json",
                                   json.dumps(atlas).encode(), "wrong-sheet-name.zip")
        self.assertFalse(self.inspect(wrong_image)["valid"])

        with zipfile.ZipFile(archive) as source:
            runtime = json.loads(source.read("metadata/fish_walk.json"))
        runtime["atlas_frames"]["walk_00.png"]["anchor"] = {"x": 999, "y": 999}
        wrong_anchor = self.replace(archive, "metadata/fish_walk.json",
                                    json.dumps(runtime).encode(), "bad-anchor.zip")
        self.assertFalse(self.inspect(wrong_anchor)["valid"])

        runtime["atlas_frames"]["walk_00.png"]["anchor"] = self.cfg.anchor
        runtime["sheet"] = "missing.png"
        wrong_runtime_sheet = self.replace(archive, "metadata/fish_walk.json",
                                           json.dumps(runtime).encode(), "bad-runtime-sheet.zip")
        self.assertFalse(self.inspect(wrong_runtime_sheet)["valid"])

        manifest["actions"] = []
        changed_manifest = self.replace(archive, "fish_manifest.json",
                                        json.dumps(manifest).encode(), "bad-manifest.zip")
        report = self.inspect(changed_manifest)
        self.assertFalse(report["valid"])
        self.assertTrue(any(issue["path"] == "fish_manifest.json" for issue in report["issues"]))

        with zipfile.ZipFile(archive) as source:
            manifest = json.loads(source.read("fish_manifest.json"))
        manifest["actions"][0]["preview"] = "missing.webp"
        wrong_preview_link = self.replace(archive, "fish_manifest.json",
                                          json.dumps(manifest).encode(), "bad-preview-link.zip")
        self.assertFalse(self.inspect(wrong_preview_link)["valid"])

    def test_preview_or_playback_record_corruption_fails(self):
        archive = self.export()
        bad_webp = self.replace(archive, "webp/fish_walk.webp", b"broken", "bad-webp.zip")
        report = self.inspect(bad_webp)
        self.assertFalse(report["valid"])
        self.assertTrue(any("webp/fish_walk.webp" in issue["path"] for issue in report["issues"]))

        with zipfile.ZipFile(archive) as source:
            record = json.loads(source.read("webp/fish_walk.animation.json"))
        record["steps"][0]["duration_ms"] = 999
        wrong_record = self.replace(archive, "webp/fish_walk.animation.json",
                                    json.dumps(record).encode(), "bad-record.zip")
        report = self.inspect(wrong_record)
        self.assertFalse(report["valid"])
        self.assertTrue(any("webp/fish_walk.animation.json" in issue["path"] for issue in report["issues"]))

    def test_webp_per_frame_timing_is_checked_even_when_total_is_unchanged(self):
        archive = self.export()
        with zipfile.ZipFile(archive) as source:
            blob = bytearray(source.read("webp/fish_walk.webp"))
        positions, offset = [], 12
        while offset + 8 <= len(blob):
            length = int.from_bytes(blob[offset + 4:offset + 8], "little")
            if blob[offset:offset + 4] == b"ANMF":
                positions.append(offset + 20)
            offset += 8 + length + (length & 1)
        self.assertEqual(len(positions), 3)
        blob[positions[0]:positions[0] + 3] = (90).to_bytes(3, "little")
        blob[positions[1]:positions[1] + 3] = (130).to_bytes(3, "little")
        altered = self.replace(archive, "webp/fish_walk.webp", bytes(blob), "wrong-timing.zip")
        report = self.inspect(altered)
        self.assertFalse(report["valid"])
        self.assertTrue(any("webp/fish_walk.webp" == issue["path"] for issue in report["issues"]))

    def test_adjacent_repeated_pose_is_checked_when_encoder_combines_frames(self):
        self.cfg.data["actions"]["walk"]["animation"]["order"] = [0, 0, 1]
        write_json(self.cfg.path, self.cfg.data)
        self.cfg = load_config(self.cfg.path)
        report = self.inspect(self.export())
        self.assertTrue(report["valid"], report["issues"])

    def test_gif_with_wrong_transparency_fails(self):
        from sprite_pipeline.gif import encode_gif
        archive = self.export()
        frames = []
        for x in (1, 7, 1):
            image = Image.new("RGBA", self.cfg.size, (0, 0, 0, 0))
            image.paste("purple", (x, 10, x + 4, 14))
            frames.append(image)
        altered = self.replace(archive, "gif/fish_walk.gif",
                               encode_gif(frames, [100, 120, 80], 1), "wrong-gif.zip")
        report = self.inspect(altered)
        self.assertFalse(report["valid"])
        self.assertTrue(any("gif/fish_walk.gif" == issue["path"] for issue in report["issues"]))

    def test_gif_with_correct_shape_but_wrong_colors_or_static_frame_fails(self):
        from sprite_pipeline.gif import encode_gif
        archive = self.export()
        frames = []
        for x in (1, 7, 1):
            image = Image.new("RGBA", self.cfg.size, (0, 0, 0, 0))
            image.paste("green", (x, 4, x + 4, 9))
            frames.append(image)
        wrong_colors = self.replace(archive, "gif/fish_walk.gif",
                                    encode_gif(frames, [100, 120, 80], 1), "wrong-colors.zip")
        self.assertFalse(self.inspect(wrong_colors)["valid"])
        wrong_static = self.replace(archive, "gif/fish_walk.gif",
                                    encode_gif([frames[0]], [300], 1), "wrong-static.zip")
        self.assertFalse(self.inspect(wrong_static)["valid"])

    def test_gif_palette_loss_on_rich_color_frames_is_accepted(self):
        for index in range(2):
            image = Image.new("RGBA", self.cfg.size)
            for y in range(16):
                for x in range(16):
                    image.putpixel((x, y), ((x * 16 + index * 3) % 256,
                                                y * 16, (x * 9 + y * 7) % 256, 255))
            image.save(self.cfg.directory("processed_sprites") / f"walk/{index:03d}.png")
        report = self.inspect(self.export("gif"))
        self.assertTrue(report["valid"], report["issues"])

    def test_large_rich_color_gif_uses_palette_rule_without_false_alarm(self):
        self.store.create("Rich", "rich", frame_size=[128, 128])
        cfg = load_config(self.workspaces / "rich/pipeline.json")
        folder = cfg.directory("processed_sprites") / "paint"
        folder.mkdir(parents=True)
        for index in range(2):
            image = Image.new("RGBA", cfg.size)
            for y in range(128):
                for x in range(128):
                    image.putpixel((x, y), ((x * 71 + y * 13 + index) % 256,
                                                (x * 3 + y * 29) % 256,
                                                (x * 17 + y * 5) % 256, 255))
            image.save(folder / f"{index:03d}.png")
        cfg.data["actions"]["paint"] = {"sprites": ["paint/000.png", "paint/001.png"], "fps": 10}
        write_json(cfg.path, cfg.data)
        cfg = load_config(cfg.path)
        content, _, _ = self.store.get("rich").export(cfg.data, {"format": "gif", "actions": ["paint"]})
        archive = self.root / "rich.gif.zip"
        archive.write_bytes(content)
        from sprite_pipeline.export_check import check_export
        report = check_export(cfg, archive)
        self.assertTrue(report["valid"], report["issues"])

    def test_localized_color_corruption_in_rich_gif_is_detected(self):
        from sprite_pipeline.gif import encode_gif
        for index in range(2):
            image = Image.new("RGBA", self.cfg.size)
            for y in range(16):
                for x in range(16):
                    image.putpixel((x, y), ((x * 16 + index * 3) % 256,
                                                y * 16, (x * 9 + y * 7) % 256, 255))
            image.save(self.cfg.directory("processed_sprites") / f"walk/{index:03d}.png")
        archive = self.export("gif")
        with Image.open(self.cfg.directory("processed_sprites") / "walk/000.png") as image:
            first = image.convert("RGBA")
        with Image.open(self.cfg.directory("processed_sprites") / "walk/001.png") as image:
            second = image.convert("RGBA")
        altered = first.copy()
        for y in range(2):
            for x in range(4):
                altered.putpixel((x, y), (255, 0, 255, 255))
        tampered = self.replace(archive, "gif/fish_walk.gif",
                                encode_gif([altered, second, altered], [100, 120, 80], 1),
                                "localized-color.zip")
        self.assertFalse(self.inspect(tampered)["valid"])

    def test_all_identical_webp_steps_may_become_one_static_image(self):
        self.cfg.data["actions"]["walk"]["animation"]["order"] = [0, 0, 0]
        write_json(self.cfg.path, self.cfg.data)
        self.cfg = load_config(self.cfg.path)
        report = self.inspect(self.export("webp"))
        self.assertTrue(report["valid"], report["issues"])

    def test_expected_format_and_actions_detect_missing_resource_groups(self):
        from sprite_pipeline.export_check import check_export
        archive = self.export("webp")
        report = check_export(self.cfg, archive, expect_format="all", expected_actions=["walk"])
        self.assertFalse(report["valid"])
        self.assertTrue(any("gif" in issue["message"] for issue in report["issues"]))
        self.assertTrue(check_export(self.cfg, archive, expect_format="webp", expected_actions=["walk"])["valid"])
        report = check_export(self.cfg, archive, expected_actions=["missing"])
        self.assertFalse(report["valid"])

    def test_requiring_one_action_still_checks_other_included_actions(self):
        from sprite_pipeline.export_check import check_export
        self.cfg.data["actions"]["other"] = {"sprites": ["walk/000.png"], "fps": 10}
        write_json(self.cfg.path, self.cfg.data)
        self.cfg = load_config(self.cfg.path)
        content, _, _ = self.store.get("fish").export(
            self.cfg.data, {"format": "frames", "actions": ["walk", "other"]})
        archive = self.root / "two-actions.zip"
        archive.write_bytes(content)
        wrong = io.BytesIO()
        Image.new("RGBA", self.cfg.size, "purple").save(wrong, "PNG")
        altered = self.replace(archive, "sprites/other/other_00.png", wrong.getvalue(), "wrong-other.zip")
        report = check_export(self.cfg, altered, expected_actions=["walk"])
        self.assertFalse(report["valid"])
        self.assertTrue(any(issue["path"] == "sprites/other/other_00.png" for issue in report["issues"]))

    def test_old_project_state_and_project_backup_are_not_claimed_valid(self):
        archive = self.export()
        image = Image.new("RGBA", self.cfg.size, "green")
        image.save(self.cfg.directory("processed_sprites") / "walk/000.png")
        self.assertFalse(self.inspect(archive)["valid"])
        project = self.export("project")
        report = self.inspect(project)
        self.assertFalse(report["valid"])
        self.assertTrue(any("backup" in issue["message"] for issue in report["issues"]))

    def test_cli_returns_failure_json_for_corrupt_archive(self):
        archive = self.export()
        bad = self.replace(archive, "webp/fish_walk.webp", b"broken", "cli-bad.zip")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = manage(["--workspace-root", str(self.workspaces), "--json",
                               "check-export", "fish", "--archive", str(bad)])
            except SystemExit as error:
                code = error.code
        self.assertEqual(code, 1, stderr.getvalue())
        self.assertFalse(json.loads(stdout.getvalue())["valid"])
