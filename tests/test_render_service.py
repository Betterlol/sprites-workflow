"""Render results must remain independent of later previews and filesystem writes."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class RenderServiceTests(unittest.TestCase):
    def test_results_keep_their_own_versions_and_preview_never_writes(self):
        from sprite_pipeline.application.rendering import RenderService
        from sprite_pipeline.config import config_from_data

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'source').mkdir()
            Image.new('RGBA', (8, 4), 'red').save(root / 'source' / 'idle.png')
            data = {
                'version': 2, 'character': 'test', 'frame_size': [16, 16],
                'sources': {'idle.png': {'extract': {'method': 'grid', 'cols': 2, 'rows': 1}}},
                'actions': {},
            }
            cfg = config_from_data(data, root / 'pipeline.json')
            before = sorted(p.relative_to(root) for p in root.rglob('*'))
            renderer = RenderService()
            first = renderer.render(cfg, 'idle.png')
            original_versions = dict(first.versions)
            data['sources']['idle.png']['process'] = {'overrides': {'001': {'offset': [1, 0]}}}
            second = renderer.render(config_from_data(data, cfg.path), 'idle.png')
            self.assertEqual(first.versions, original_versions)
            self.assertEqual(second.versions['000.png'], original_versions['000.png'])
            self.assertNotEqual(second.versions['001.png'], original_versions['001.png'])
            self.assertIs(first.frames['000.png'], second.frames['000.png'])
            self.assertEqual([d['file'] for d in first.descriptors], ['000.png', '001.png'])
            self.assertEqual(sorted(p.relative_to(root) for p in root.rglob('*')), before)
            self.assertEqual(renderer.render(cfg, 'idle.png', 'extract').frames['000.png'].size, (4, 4))
            with self.assertRaises(ValueError):
                renderer.render(cfg, 'idle.png', 'invalid')


if __name__ == '__main__':
    unittest.main()
