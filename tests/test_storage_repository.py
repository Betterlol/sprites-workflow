"""Config persistence returns a revision for the exact snapshot it read."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class ConfigRepositoryTests(unittest.TestCase):
    def test_snapshot_revision_and_failed_save_preserve_disk(self):
        from sprite_pipeline.storage.configuration import ConfigRepository
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'pipeline.json'
            data = {'version': 2, 'character': 'test', 'frame_size': [16, 16], 'actions': {}}
            path.write_text(json.dumps(data), encoding='utf-8')
            before = path.read_bytes()
            repository = ConfigRepository(path)
            snapshot = repository.snapshot()
            self.assertEqual(snapshot.revision, hashlib.sha256(before).hexdigest())
            self.assertEqual(snapshot.config.character, 'test')
            with self.assertRaises(TypeError):
                repository.save({**data, 'unserializable': object()})
            self.assertEqual(path.read_bytes(), before)
            repository.save({**data, 'project': {'name': 'renamed'}})
            self.assertEqual(repository.load().data['project']['name'], 'renamed')
            self.assertNotEqual(repository.revision, snapshot.revision)


if __name__ == '__main__':
    unittest.main()
