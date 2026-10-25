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
from sprite_pipeline.extract import cut_frames, extract_source
from sprite_pipeline.files import read_image
from sprite_pipeline.process import process_source
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
            "version": 2, "character": "test", "frame_size": [16, 16],
            "anchor": {"x": 0.5, "y": 0.875, "pixels": [8, 14]},
            "defaults": {"fps": 10, "loop": False, "process": {"mode": "copy"}},
            "sources": {"walk.png": {"extract": {"method": "grid", "cols": 3, "rows": 1}}},
            "actions": {"walk": {
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
        extract_source(cfg, "walk.png")
        process_source(cfg, "walk.png")
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

    def test_component_extraction_discovers_layout_without_action_or_grid(self):
        image = Image.new("RGBA", (40, 40))
        boxes = [(2, 2, 10, 10), (24, 3, 32, 11), (2, 25, 10, 33), (24, 24, 32, 32)]
        for box, color in zip(boxes, ("red", "green", "blue", "yellow")):
            image.paste(color, box)
        frames, found = cut_frames(image, {"min_component_pixels": 1, "major_min_pixels": 4, "major_fraction": 0})
        self.assertEqual(found, boxes)
        self.assertEqual(len(frames), 4)

    def test_explicit_boxes_are_exact_and_invalid_boxes_are_rejected(self):
        source = read_image(self.source / "walk.png")
        frames, _ = cut_frames(source, {"method": "boxes", "boxes": [[32, 0, 48, 16], [0, 0, 16, 16]]})
        self.assertEqual(frames[0].getpixel((0, 0)), (0, 0, 255, 255))
        with self.assertRaises(ValueError):
            cut_frames(source, {"method": "boxes", "boxes": [[-1, 0, 2, 2]]})

    def test_processing_uses_one_scale_and_configured_offsets(self):
        self.data["frame_size"] = [32, 32]
        self.data["anchor"] = {"x": 0.5, "y": 0.875, "pixels": [16, 28]}
        self.data["sources"]["walk.png"] = {
            "extract": {"method": "grid", "cols": 2, "rows": 1},
            "process": {
                "mode": "anchor", "fit_height": 10, "max_scale": 1,
                "overrides": {"001": {"offset": [2, -3]}},
            },
        }
        sheet = Image.new("RGBA", (16, 20))
        sheet.paste(Image.new("RGBA", (8, 20), "red"), (0, 0))
        sheet.paste(Image.new("RGBA", (8, 10), "blue"), (8, 0))
        sheet.save(self.source / "walk.png")
        cfg = self.config()
        extract_source(cfg, "walk.png")
        process_source(cfg, "walk.png")
        tall = read_image(cfg.directory("processed_sprites") / "walk/000.png")
        short = read_image(cfg.directory("processed_sprites") / "walk/001.png")
        self.assertEqual(tall.getbbox(), (14, 18, 18, 28))
        self.assertEqual(short.getbbox(), (16, 20, 20, 25))
        self.assertFalse(cfg.directory("sprites").exists())

    def test_promotion_copies_processed_bytes_and_removes_stale_numbers(self):
        self.data["actions"]["walk"]["sprites"] = ["walk/000.png", "walk/002.png", "walk/000.png"]
        cfg = self.prepare()
        approved = cfg.directory("processed_sprites") / "walk/000.png"
        Image.new("RGBA", cfg.size, "yellow").save(approved, compress_level=1)
        select_action(cfg, "walk")
        final = cfg.directory("sprites") / "walk"
        self.assertEqual((final / "walk_00.png").read_bytes(), approved.read_bytes())
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

    def test_gif_animation_clears_moving_frames_and_rounds_timing(self):
        from sprite_pipeline.gif import encode_gif
        frames = []
        for index, color in enumerate(("red", "green", "blue")):
            frame = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
            frame.paste(color, (index * 4 + 1, 4, index * 4 + 5, 8))
            frames.append(frame)
        content = encode_gif(frames, [62, 100, 120], 2)
        with Image.open(io.BytesIO(content)) as gif:
            self.assertEqual(gif.n_frames, 3)
            self.assertEqual(gif.info["loop"], 1)  # GIF stores repeats after the first pass.
            for index, duration in enumerate((60, 100, 120)):
                gif.seek(index)
                image = gif.convert("RGBA")
                self.assertEqual(gif.info["duration"], duration)
                self.assertEqual(gif.disposal_method, 2)
                self.assertEqual(image.getbbox(), (index * 4 + 1, 4, index * 4 + 5, 8))
                self.assertEqual(image.getpixel((1, 4))[3], 255 if index == 0 else 0)
        once = encode_gif(frames, [100] * 3, 1)
        with Image.open(io.BytesIO(once)) as gif:
            self.assertNotIn("loop", gif.info)

    def test_gif_keeps_the_color_of_a_retained_antialiased_edge(self):
        from sprite_pipeline.gif import encode_gif
        first = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        first.putpixel((3, 3), (255, 255, 255, 128))
        second = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        second.putpixel((4, 3), (255, 0, 0, 255))
        with Image.open(io.BytesIO(encode_gif([first, second], [100, 100], 1))) as gif:
            self.assertEqual(gif.convert("RGBA").getpixel((3, 3)), (255, 255, 255, 255))

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
        extract_source(cfg, "walk.png")
        process_source(cfg, "walk.png")
        self.assertEqual(final.read_bytes(), before)

    def test_single_action_pack_preserves_other_actions_and_manifest_entries(self):
        self.data["actions"]["rest"] = {"sprites": ["walk/000.png", "walk/001.png"]}
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
        self.data["sources"]["walk.png"]["process"] = {"mode": "anchor", "scale": 2}
        with self.assertRaisesRegex(ValueError, "clipped"):
            process_source(self.config(), "walk.png")
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

    def test_all_originals_are_discovered_and_processed_before_actions_exist(self):
        self.data["actions"] = {}
        self.data["defaults"]["extract"] = {"min_component_pixels": 1, "major_min_pixels": 4, "major_fraction": 0}
        # This original has no per-file rule and is not referenced by any action.
        Image.new("RGBA", (16, 16), "purple").save(self.source / "unused.png")
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        cfg = self.config()
        for stage in ("extract", "process"):
            status, error = self.run_cli(stage)
            self.assertEqual(status, 0, error)
        self.assertEqual(cfg.discover_sources(), ["unused.png", "walk.png"])
        self.assertTrue((cfg.directory("source_sprites") / "unused/000.png").exists())
        self.assertTrue((cfg.directory("processed_sprites") / "unused/000.png").exists())
        self.assertTrue((cfg.directory("processed_sprites") / "walk/002.png").exists())
        self.assertFalse(cfg.directory("sprites").exists())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_two_actions_reuse_the_same_processed_frame_without_copying_into_source(self):
        self.data["actions"]["rest"] = {"sprites": ["walk/000.png", "walk/002.png"]}
        cfg = self.config()
        status, error = self.run_cli("build", "--no-preview")
        self.assertEqual(status, 0, error)
        common = (cfg.directory("processed_sprites") / "walk/002.png").read_bytes()
        self.assertEqual((cfg.directory("sprites") / "walk/walk_00.png").read_bytes(), common)
        self.assertEqual((cfg.directory("sprites") / "rest/rest_01.png").read_bytes(), common)
        self.assertEqual([p.name for p in self.source.iterdir()], ["walk.png"])

    def test_single_action_build_still_prepares_every_original(self):
        self.data["sources"]["unused.png"] = {"extract": {"method": "image"}}
        Image.new("RGBA", (16, 16), "yellow").save(self.source / "unused.png")
        cfg = self.config()
        status, error = self.run_cli("build", "--action", "walk", "--no-preview")
        self.assertEqual(status, 0, error)
        self.assertTrue((cfg.directory("processed_sprites") / "unused/000.png").exists())

    def test_source_filter_uses_original_filename_and_mirrors_subdirectories(self):
        (self.source / "extra").mkdir()
        image = Image.new("RGBA", (16, 16), "yellow")
        image.save(self.source / "extra/pose.png")
        self.data["sources"]["extra/pose.png"] = {"extract": {"method": "image"}}
        cfg = self.config()
        for stage in ("extract", "process"):
            status, error = self.run_cli(stage, "--source", "extra/pose.png")
            self.assertEqual(status, 0, error)
        output = cfg.directory("processed_sprites") / "extra/pose/000.png"
        self.assertEqual(read_image(output).tobytes(), image.tobytes())
        self.assertFalse((cfg.directory("processed_sprites") / "walk").exists())

    def test_original_and_action_filters_cannot_be_confused(self):
        cfg = self.config()
        for arguments in (("extract", "--action", "walk"), ("process", "--action", "walk"), ("pack", "--source", "walk.png"), ("extract", "--source", "missing.png")):
            with self.subTest(arguments=arguments):
                status, _ = self.run_cli(*arguments)
                self.assertEqual(status, 1)
        self.assertFalse(cfg.directory("source_sprites").exists())

    def test_source_rules_cannot_silently_skip_missing_images_or_collide_outputs(self):
        self.data["sources"]["missing.png"] = {"extract": {"method": "image"}}
        cfg = self.config()
        with self.assertRaisesRegex(ValueError, "missing images"):
            cfg.discover_sources()
        del self.data["sources"]["missing.png"]
        Image.new("RGB", (16, 16), "yellow").save(self.source / "walk.jpg")
        with self.assertRaisesRegex(ValueError, "same output directory"):
            self.config().discover_sources()

    def test_legacy_action_extraction_and_source_imports_are_rejected(self):
        baseline = copy.deepcopy(self.data)
        for field in ("extract", "process", "imports"):
            self.data = copy.deepcopy(baseline)
            self.data["actions"]["walk"][field] = {}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "actions only assemble"):
                self.config()
        self.data = copy.deepcopy(baseline)
        self.data["defaults"]["process"]["inputs"] = {"start": {"file": "legacy_start.png"}}
        with self.assertRaisesRegex(ValueError, "no longer supported"):
            self.config()


if __name__ == "__main__":
    unittest.main()
