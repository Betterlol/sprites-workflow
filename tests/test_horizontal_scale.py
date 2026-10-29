"""Horizontal scaling preserves height, anchors, inheritance and cache isolation."""

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.domain.models import CanvasSpec
from sprite_pipeline.imaging.processing import normalize, process_frames
from sprite_pipeline.storage.cache import RenderCache
from sprite_pipeline.storage.configuration import config_from_data


class HorizontalScaleTests(unittest.TestCase):
    def setUp(self):
        self.canvas = CanvasSpec((32, 32), {"pixels": [16, 28]})
        self.sprite = Image.new("RGBA", (8, 8), "red")

    def test_group_horizontal_scale_follows_fit_height_and_preserves_anchor(self):
        result = process_frames(
            self.canvas,
            "idle.png",
            {"fit_height": 16, "max_scale": 2, "scale_x": 0.5},
            {"000": self.sprite},
        )
        self.assertEqual(result.scale, 2)
        self.assertEqual(result.frames["000.png"].getbbox(), (12, 12, 20, 28))

    def test_contain_horizontal_scale_keeps_vertical_center(self):
        result = normalize(
            Image.new("RGBA", (8, 4), "red"),
            self.canvas,
            {"mode": "contain", "scale_x": 0.5, "offset": [2, -1]},
            0.5,
        )
        self.assertEqual(result.getbbox(), (14, 11, 22, 19))

    def test_frame_override_is_absolute_and_does_not_double_apply_scale(self):
        result = process_frames(
            self.canvas,
            "idle.png",
            {"scale": 0.5, "scale_x": 0.5, "overrides": {"001": {"scale": 1.5, "scale_x": 0.25}}},
            {"000": self.sprite, "001": self.sprite},
        )
        self.assertEqual(result.frames["000.png"].getbbox(), (15, 24, 17, 28))
        self.assertEqual(result.frames["001.png"].getbbox(), (14, 16, 17, 28))

    def test_frame_horizontal_override_invalidates_only_its_cached_frame(self):
        cache = RenderCache()
        images = {"000": self.sprite, "001": self.sprite}
        first = process_frames(self.canvas, "idle.png", {"scale_x": 0.5}, images, cache=cache)
        second = process_frames(
            self.canvas,
            "idle.png",
            {"scale_x": 0.5, "overrides": {"001": {"scale_x": 0.25}}},
            images,
            cache=cache,
        )
        self.assertEqual(first.versions["000.png"], second.versions["000.png"])
        self.assertIs(first.frames["000.png"], second.frames["000.png"])
        self.assertNotEqual(first.versions["001.png"], second.versions["001.png"])
        self.assertEqual(second.frames["001.png"].getbbox(), (15, 20, 17, 28))
        inherited = process_frames(
            self.canvas,
            "idle.png",
            {"scale_x": 0.5, "overrides": {"001": {}}},
            images,
            cache=cache,
        )
        self.assertIs(inherited.frames["001.png"], first.frames["001.png"])

    def test_horizontal_expansion_uses_existing_overflow_policy(self):
        with self.assertRaisesRegex(ValueError, "clipped"):
            normalize(self.sprite, self.canvas, {"scale_x": 5}, 1)
        clipped = normalize(self.sprite, self.canvas, {"scale_x": 5, "overflow": "clip"}, 1)
        self.assertEqual(clipped.getbbox(), (0, 20, 32, 28))

    def test_copy_rejects_horizontal_changes_including_frame_overrides(self):
        image = Image.new("RGBA", self.canvas.size, "red")
        self.assertIs(normalize(image, self.canvas, {"mode": "copy", "scale_x": 1}, 1), image)
        for settings in (
            {"mode": "copy", "scale_x": 0.5},
            {"mode": "copy", "overrides": {"000": {"scale_x": 0.5}}},
        ):
            with (
                self.subTest(settings=settings),
                self.assertRaisesRegex(ValueError, "copy.*scale_x"),
            ):
                process_frames(self.canvas, "idle.png", settings, {"000": image})

    def test_invalid_horizontal_scales_fail_at_configuration_boundary(self):
        invalid = (0, -1, float("nan"), float("inf"), -float("inf"), True, "0.5", None)
        with tempfile.TemporaryDirectory() as temporary:
            for value in invalid:
                for location in ("defaults", "source", "default_override", "source_override"):
                    with self.subTest(value=value, location=location):
                        data = {
                            "version": 2,
                            "character": "test",
                            "frame_size": [32, 32],
                            "actions": {},
                        }
                        rules = {"scale_x": value}
                        if location.endswith("override"):
                            rules = {"overrides": {"000": rules}}
                        if location.startswith("default"):
                            data["defaults"] = {"process": rules}
                        else:
                            data["sources"] = {"idle.png": {"process": rules}}
                        with self.assertRaisesRegex(ValueError, "scale_x"):
                            config_from_data(data, Path(temporary) / "pipeline.json")

    def test_invalid_horizontal_scales_fail_before_processing_in_any_mode(self):
        for mode in ("anchor", "contain", "copy"):
            for value in (0, -1, float("nan"), float("inf"), True, None):
                with (
                    self.subTest(mode=mode, value=value),
                    self.assertRaisesRegex(ValueError, "scale_x"),
                ):
                    normalize(self.sprite, self.canvas, {"mode": mode, "scale_x": value}, 1)


if __name__ == "__main__":
    unittest.main()
