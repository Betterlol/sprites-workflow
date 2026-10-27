"""Verified native slices. Their validity does not depend on processing settings."""
from __future__ import annotations

import hashlib
import io
import json
import re
from PIL import Image

from .config import Config, inside
from .files import replace_frames


def extraction_fingerprint(cfg: Config, filename: str) -> str:
    digest = hashlib.sha256(inside(cfg.source, filename).read_bytes())
    digest.update(json.dumps(cfg.source_spec(filename)['extract'], sort_keys=True).encode())
    return digest.hexdigest()


def read_slices(cfg: Config, filename: str):
    """Return verified images/descriptors, or None for absent, stale or corrupt cache."""
    directory = inside(cfg.directory('source_sprites'), cfg.source_id(filename))
    try:
        stage = json.loads((directory / '_stage.json').read_text(encoding='utf-8'))
        if (stage.get('stage') != 'extract' or stage.get('source') != filename
                or stage.get('fingerprint') != extraction_fingerprint(cfg, filename)):
            return None
        descriptors = stage['frames']
        authored = cfg.source_spec(filename)['extract'].get('identities')
        if authored and descriptors != authored:
            return None
        names = [frame['file'] for frame in descriptors]
        if (not names or len(set(names)) != len(names) or names != stage['files']
                or any(not re.fullmatch(r'\d+\.png', name) for name in names)):
            return None
        images = {}
        for item in descriptors:
            path = inside(directory, item['file'])
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != stage['digests'][item['file']]:
                return None
            with Image.open(io.BytesIO(content)) as opened:
                image = opened.convert('RGBA')
            x, y, right, bottom = item['source_box']
            if image.size != (right-x, bottom-y):
                return None
            images[path.stem] = image
        return images, descriptors
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def write_slices(cfg: Config, filename: str, images: dict, descriptors: list) -> None:
    frames = {f'{key}.png': image for key, image in images.items()}
    digests = {}
    for name, image in frames.items():
        buffer = io.BytesIO()
        image.save(buffer, format='PNG', optimize=True)
        digests[name] = hashlib.sha256(buffer.getvalue()).hexdigest()
    replace_frames(inside(cfg.directory('source_sprites'), cfg.source_id(filename)), frames,
                   owned=r'\d+\.png', metadata={'stage':'extract', 'source':filename,
                   'files':list(frames), 'frames':descriptors, 'digests':digests,
                   'fingerprint':extraction_fingerprint(cfg, filename)})
