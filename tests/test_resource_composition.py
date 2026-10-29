"""Contract examples for nested resources. Not executed during this delivery."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.domain.resources import resolve_resource, sprite_users, validate_resources


def slot(kind, ref, identity, **options):
    return {"id": identity, "resource": {"kind": kind, "ref": ref}, **options}


class ResourceCompositionTests(unittest.TestCase):
    def project(self):
        return {
            "defaults": {"fps": 12},
            "actions": {"base": {"fps": 20, "loop": True, "sprites": ["red.png", "green.png"]}},
            "workbench": {
                "reviews": {
                    "bridge": {
                        "mode": "runtime",
                        "slots": [
                            slot("sprite", "blue.png", "pose", duration_ms=120),
                            slot("action", "base", "finish", start=1, end=1, repeat=2, speed=2),
                        ],
                    }
                }
            },
        }

    def test_action_sequence_and_single_frames_share_finite_timing_and_provenance(self):
        data = self.project()
        data["actions"]["combo"] = {
            "slots": [
                slot("action", "base", "begin"),
                slot("sequence", "bridge", "middle", speed=2),
                slot("sprite", "red.png", "hold", duration_ms=80, repeat=2),
            ]
        }
        result = resolve_resource(data, "action", "combo")
        self.assertEqual(
            [s["ref"] for s in result],
            ["red.png", "green.png", "blue.png", "green.png", "green.png", "red.png", "red.png"],
        )
        self.assertEqual([s["duration_ms"] for s in result], [50, 50, 60, 12, 12, 80, 80])
        self.assertEqual([s["slot"] for s in result], [0, 0, 1, 1, 1, 2, 2])
        self.assertEqual(result[3]["lineage"][1]["ref"], "bridge")
        self.assertEqual(len({tuple(s["origin"]) for s in result}), 7)
        self.assertIn("sequence:bridge", sprite_users(data)["blue.png"])

    def test_display_reference_is_finite_and_root_display_preserves_child_time(self):
        data = self.project()
        data["actions"]["base"]["animation"] = {"order": [1, 0, 1], "durations_ms": [60, 90, 30]}
        data["actions"]["combo"] = {"slots": [slot("action", "base", "shown", mode="display")]}
        self.assertEqual(
            [s["duration_ms"] for s in resolve_resource(data, "action", "combo", "display")],
            [60, 90, 30],
        )
        data["actions"]["combo"]["animation"] = {"order": [2, 0]}
        result = resolve_resource(data, "action", "combo", "display")
        self.assertEqual([s["frame"] for s in result], [2, 0])
        self.assertEqual([s["duration_ms"] for s in result], [30, 60])

    def test_cross_kind_cycle_and_missing_resource_are_rejected(self):
        data = self.project()
        data["actions"]["base"] = {"slots": [slot("sequence", "bridge", "cycle")]}
        with self.assertRaisesRegex(ValueError, "Circular"):
            validate_resources(data)
        data["actions"]["base"]["slots"][0]["resource"]["ref"] = "missing"
        with self.assertRaisesRegex(ValueError, "Unknown"):
            validate_resources(data)

    def test_ranges_and_expanded_size_are_bounded(self):
        data = self.project()
        data["actions"]["combo"] = {"slots": [slot("action", "base", "bad-range", start=2)]}
        with self.assertRaisesRegex(ValueError, "range"):
            resolve_resource(data, "action", "combo")
        data["actions"]["base"]["sprites"] = ["red.png"] * 100
        data["actions"]["combo"]["slots"] = [
            slot("action", "base", "full", repeat=100),
            slot("sprite", "red.png", "overflow"),
        ]
        with self.assertRaisesRegex(ValueError, "10,000"):
            resolve_resource(data, "action", "combo")
