"""Behavior checks for stage boundaries, promotion and independent playback."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.animation import playback
from sprite_pipeline.cli import main
from sprite_pipeline.config import load_config
from sprite_pipeline.export import pack_action, preview_action
from sprite_pipeline.extract import cut_frames, extract_action
from sprite_pipeline.files import read_image
from sprite_pipeline.process import process_action
from sprite_pipeline.select import select_action


class SpritePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config_path = self.root / "pipeline.json"
        self.source = self.root / "source"
        self.source.mkdir()
        self.data = {
            "version": 1, "character": "test", "frame_size": [16, 16],
            "anchor": {"x": 0.5, "y": 0.875, "pixels": [8, 14]},
            "defaults": {"fps": 10, "loop": False, "process": {"mode": "copy"}},
            "actions": {"walk": {
                "extract": {"file": "walk.png", "method": "grid", "cols": 3, "rows": 1},
                "sprites": ["walk/002.png", "walk/000.png", "walk/001.png"],
            }},
        }
        sheet = Image.new("RGBA", (48, 16))
        for i, color in enumerate(("red", "green", "blue")):
            sheet.paste(Image.new("RGBA", (16, 16), color), (i * 16, 0))
        sheet.save(self.source / "walk.png")

    def config(self, output_root=None):
        self.config_path.write_text(json.dumps(self.data), encoding="utf-8")
        return load_config(self.config_path, output_root)

    def prepare(self):
        cfg = self.config()
        extract_action(cfg, "walk")
        process_action(cfg, "walk")
        select_action(cfg, "walk")
        return cfg

    def run_cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = main(self.config_path, list(args))
        return status, stderr.getvalue()

    def test_grid_slices_preserve_native_pixels_and_uneven_dimensions(self):
        image = Image.new("RGBA", (7, 5))
        image.putdata([(x, y, 50, 255) for y in range(5) for x in range(7)])
        frames, boxes = cut_frames(image, {"method": "grid", "cols": 3, "rows": 2})
        reconstructed = Image.new("RGBA", image.size)
        for frame, box in zip(frames, boxes):
            self.assertEqual(frame.size, (box[2] - box[0], box[3] - box[1]))
            reconstructed.paste(frame, box[:2])
        self.assertEqual(image.tobytes(), reconstructed.tobytes())

    def test_component_extraction_keeps_spill_and_assigns_detached_effect(self):
        image = Image.new("RGBA", (30, 16))
        image.paste((255, 0, 0, 255), (2, 3, 17, 10))  # Crosses nominal grid boundary.
        image.paste((0, 0, 255, 255), (23, 3, 28, 10))
        image.putpixel((19, 5), (255, 255, 255, 255))
        frames, boxes = cut_frames(image, {
            "method": "components", "cols": 2, "rows": 1,
            "min_component_pixels": 1, "major_min_pixels": 10, "major_fraction": 0,
        })
        self.assertEqual(boxes, [(2, 3, 20, 10), (23, 3, 28, 10)])
        self.assertEqual(frames[0].getpixel((17, 2)), (255, 255, 255, 255))
        self.assertEqual(frames[0].getpixel((16, 2))[3], 0)

    def test_explicit_boxes_are_exact_and_invalid_boxes_are_rejected(self):
        source = read_image(self.source / "walk.png")
        frames, _ = cut_frames(source, {"method": "boxes", "boxes": [[32, 0, 48, 16], [0, 0, 16, 16]]})
        self.assertEqual(frames[0].getpixel((0, 0)), (0, 0, 255, 255))
        with self.assertRaises(ValueError):
            cut_frames(source, {"method": "boxes", "boxes": [[-1, 0, 2, 2]]})

    def test_processing_uses_one_scale_and_configured_offsets(self):
        self.data["frame_size"] = [32, 32]
        self.data["anchor"] = {"x": 0.5, "y": 0.875, "pixels": [16, 28]}
        self.data["actions"]["walk"].pop("extract")
        self.data["actions"]["walk"]["process"] = {
            "mode": "anchor", "fit_height": 10, "max_scale": 1,
            "inputs": {key: {"file": f"{key}.png"} for key in ("tall", "short")},
            "overrides": {"short": {"offset": [2, -3]}},
        }
        Image.new("RGBA", (8, 20), "red").save(self.source / "tall.png")
        Image.new("RGBA", (8, 10), "blue").save(self.source / "short.png")
        cfg = self.config()
        process_action(cfg, "walk")
        tall = read_image(cfg.directory("processed_sprites") / "walk/tall.png")
        short = read_image(cfg.directory("processed_sprites") / "walk/short.png")
        self.assertEqual(tall.getbbox(), (14, 18, 18, 28))
        self.assertEqual(short.getbbox(), (16, 20, 20, 25))
        self.assertFalse(cfg.directory("source_sprites").exists())
        self.assertFalse(cfg.directory("sprites").exists())

    def test_imports_and_promotion_copy_approved_bytes_and_remove_stale_numbers(self):
        self.data["actions"]["walk"]["imports"] = {"start": "approved.png"}
        Image.new("RGBA", (16, 16), "yellow").save(self.source / "approved.png", compress_level=1)
        self.data["actions"]["walk"]["sprites"] = ["walk/start.png", "walk/002.png", "walk/start.png"]
        cfg = self.prepare()
        final = cfg.directory("sprites") / "walk"
        self.assertEqual((final / "walk_00.png").read_bytes(), (self.source / "approved.png").read_bytes())
        self.assertEqual((final / "walk_02.png").read_bytes(), (final / "walk_00.png").read_bytes())
        review = final / "review.png"
        review.write_bytes(b"user review")
        self.data["actions"]["walk"]["sprites"] = ["walk/001.png"]
        select_action(self.config(), "walk")
        self.assertFalse((final / "walk_01.png").exists())
        self.assertFalse((final / "walk_02.png").exists())
        self.assertEqual(review.read_bytes(), b"user review")

    def test_selection_failure_preserves_previous_final_frames(self):
        cfg = self.prepare()
        final = cfg.directory("sprites") / "walk"
        before = {p.name: p.read_bytes() for p in final.iterdir()}
        self.data["actions"]["walk"]["sprites"] = ["walk/000.png", "walk/missing.png"]
        with self.assertRaises(FileNotFoundError):
            select_action(self.config(), "walk")
        self.assertEqual(before, {p.name: p.read_bytes() for p in final.iterdir()})

    def test_webp_order_duration_loop_are_independent_of_runtime_atlas(self):
        self.data["actions"]["walk"]["animation"] = {
            "order": [2, 0, 1, 0], "durations_ms": [40, 120, 70, 200], "loop": 3,
        }
        cfg = self.prepare()
        pack_action(cfg, "walk")
        atlas_path = cfg.directory("spritesheets") / "test_walk.png"
        runtime_path = cfg.directory("spritesheets") / "test_walk.json"
        before = (atlas_path.read_bytes(), runtime_path.read_bytes())
        preview_action(cfg, "walk")
        atlas = read_image(atlas_path)
        self.assertEqual(atlas.getpixel((0, 0)), (0, 0, 255, 255))
        self.assertEqual(atlas.getpixel((16, 0)), (255, 0, 0, 255))
        with Image.open(cfg.directory("webp") / "test_walk.webp") as webp:
            self.assertEqual(webp.info["loop"], 3)
            self.assertEqual(webp.n_frames, 4)
            for i, (color, duration) in enumerate(zip(((0, 128, 0, 255), (0, 0, 255, 255), (255, 0, 0, 255), (0, 0, 255, 255)), (40, 120, 70, 200))):
                webp.seek(i)
                self.assertEqual(webp.convert("RGBA").getpixel((0, 0)), color)
                self.assertEqual(webp.info["duration"], duration)
        runtime = json.loads(runtime_path.read_text())
        self.assertEqual([entry["duration"] for entry in runtime["frames"].values()], [100] * 3)
        self.assertEqual(before, (atlas_path.read_bytes(), runtime_path.read_bytes()))

    def test_default_pack_preserves_manual_edits_and_needs_no_intermediate_frames(self):
        cfg = self.config()
        final = cfg.directory("sprites") / "walk"
        final.mkdir(parents=True)
        frame = final / "walk_00.png"
        Image.new("RGBA", (16, 16), "purple").save(frame)
        before = hashlib.sha256(frame.read_bytes()).hexdigest()
        status, error = self.run_cli()
        self.assertEqual(status, 0, error)
        self.assertEqual(before, hashlib.sha256(frame.read_bytes()).hexdigest())
        self.assertFalse(cfg.directory("source_sprites").exists())
        self.assertFalse(cfg.directory("processed_sprites").exists())

    def test_reprocessing_does_not_promote_or_overwrite_final_edits(self):
        cfg = self.prepare()
        final = cfg.directory("sprites") / "walk/walk_00.png"
        Image.new("RGBA", cfg.size, "purple").save(final)
        before = final.read_bytes()
        extract_action(cfg, "walk")
        process_action(cfg, "walk")
        self.assertEqual(final.read_bytes(), before)

    def test_single_action_pack_preserves_other_actions_and_manifest_entries(self):
        self.data["actions"]["rest"] = copy.deepcopy(self.data["actions"]["walk"])
        self.data["actions"]["rest"]["sprites"] = ["rest/000.png", "rest/001.png"]
        cfg = self.config()
        self.assertEqual(self.run_cli("build", "--no-preview")[0], 0)
        rest = cfg.directory("spritesheets") / "test_rest.png"
        before = rest.read_bytes()
        self.data["actions"]["walk"]["sprites"] = ["walk/000.png"]
        cfg = self.config()
        select_action(cfg, "walk")
        self.assertEqual(self.run_cli("pack", "--action", "walk", "--no-preview")[0], 0)
        manifest = json.loads((self.root / "test_manifest.json").read_text())
        self.assertEqual([(a["name"], a["count"]) for a in manifest["actions"]], [("walk", 1), ("rest", 2)])
        self.assertEqual(rest.read_bytes(), before)

    def test_preview_command_preserves_all_runtime_files_and_final_sprites(self):
        cfg = self.prepare()
        self.assertEqual(self.run_cli("pack")[0], 0)
        directories = [cfg.directory(stage) for stage in ("sprites", "spritesheets", "metadata")]
        runtime_files = [path for directory in directories for path in directory.rglob("*") if path.is_file()]
        runtime_files.append(self.root / "test_manifest.json")
        before = {path: path.read_bytes() for path in runtime_files}
        self.data["actions"]["walk"]["animation"] = {"order": [2, 0, 1, 0], "durations_ms": [40, 80, 120, 200]}
        self.config()
        status, error = self.run_cli("preview", "--action", "walk")
        self.assertEqual(status, 0, error)
        self.assertEqual(before, {path: path.read_bytes() for path in runtime_files})

    def test_numbering_gaps_and_wrong_sizes_cannot_be_packed(self):
        cfg = self.prepare()
        directory = cfg.directory("sprites") / "walk"
        (directory / "walk_01.png").unlink()
        with self.assertRaisesRegex(ValueError, "contiguous"):
            pack_action(cfg, "walk")
        select_action(cfg, "walk")
        Image.new("RGBA", (8, 8), "red").save(directory / "walk_00.png")
        with self.assertRaisesRegex(ValueError, "expected"):
            pack_action(cfg, "walk")

    def test_overflow_fails_without_replacing_previous_processed_frames(self):
        cfg = self.prepare()
        directory = cfg.directory("processed_sprites") / "walk"
        before = {path: path.read_bytes() for path in directory.iterdir()}
        self.data["actions"]["walk"]["process"] = {"mode": "anchor", "scale": 2}
        with self.assertRaisesRegex(ValueError, "clipped"):
            process_action(self.config(), "walk")
        self.assertEqual(before, {path: path.read_bytes() for path in directory.iterdir()})

    def test_invalid_preview_fails_before_changing_runtime_outputs(self):
        cfg = self.prepare()
        self.assertEqual(self.run_cli("pack")[0], 0)
        atlas = cfg.directory("spritesheets") / "test_walk.png"
        before = atlas.read_bytes()
        self.data["actions"]["walk"]["animation"] = {"order": [-1]}
        self.config()
        status, error = self.run_cli("pack")
        self.assertEqual(status, 1)
        self.assertIn("animation.order", error)
        self.assertEqual(before, atlas.read_bytes())

    def test_animation_repeated_steps_have_independent_durations(self):
        self.assertEqual(playback({"animation": {"order": [0, 0, 1], "durations_ms": [50, 100, 30]}}, 2), ([0, 0, 1], [50, 100, 30], 1))
        for animation in ({"order": [-1]}, {"order": [2]}, {"order": []}, {"durations_ms": [10]}, {"duration_ms": 0}, {"loop": -1}, {"fps": 0}):
            with self.subTest(animation=animation), self.assertRaises(ValueError):
                playback({"animation": animation}, 2)

    def test_config_rejects_unsafe_output_paths_and_overlapping_stages(self):
        original = copy.deepcopy(self.data)
        for paths in ({"sprites": "../outside"}, {"sprites": "spritesheets"}, {"spritesheets": "sprites/packed"}, {"sprites": "source/frames"}):
            self.data = copy.deepcopy(original)
            self.data["paths"] = paths
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.config()
        self.data = copy.deepcopy(original)
        self.data["actions"]["walk"]["sprites"] = ["../outside.png"]
        with self.assertRaises(ValueError):
            self.config()

    def test_full_build_can_use_an_isolated_output_root(self):
        self.config()
        alternate = self.root / "alternate"
        status, error = self.run_cli("build", "--output-root", str(alternate))
        self.assertEqual(status, 0, error)
        self.assertTrue((alternate / "sprites/walk/walk_00.png").exists())
        self.assertTrue((alternate / "spritesheets/test_walk.json").exists())
        self.assertTrue((alternate / "webp/test_walk.webp").exists())
        self.assertFalse((self.root / "sprites").exists())


if __name__ == "__main__":
    unittest.main()
