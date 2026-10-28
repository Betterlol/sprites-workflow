"""Read-only source rendering with bounded, project-local caches.

The owning project session serializes calls with its project lock.
"""
import hashlib
import json
from dataclasses import dataclass
from PIL import Image
from ..config import Config, inside
from ..domain.models import CanvasSpec, SliceDescriptor
from ..extract import previous_slices, slice_ids
from ..imaging.extraction import cut_frames
from ..imaging.processing import process_frames
from ..files import read_image
from ..slices import read_slices, extraction_fingerprint
from ..render_cache import RenderCache

@dataclass(frozen=True)
class RenderResult:
    config: Config
    raw: dict[str, Image.Image]
    frames: dict[str, Image.Image]
    descriptors: list[SliceDescriptor]
    scale: float
    versions: dict[str, str]

class RenderService:
    def __init__(self):
        self._native_cache = RenderCache()
        self._extracted_cache = RenderCache()
        self._render_cache = RenderCache()

    def render(self, cfg: Config, filename: str, stage: str = "process") -> RenderResult:
        if stage not in {"extract", "process"}:
            raise ValueError("Unknown preview stage")
        if filename not in cfg.discover_sources():
            raise ValueError("Unknown source image")
        cached = read_slices(cfg, filename, self._native_cache)
        if cached is None:
            extraction_key = extraction_fingerprint(cfg, filename) + json.dumps(previous_slices(cfg, filename), sort_keys=True)
            cached = self._extracted_cache.get(extraction_key)
            if cached is None:
                raw, boxes = cut_frames(read_image(inside(cfg.source, filename)), cfg.source_spec(filename)["extract"])
                keys = slice_ids(cfg, filename, boxes)
                images = dict(zip(keys, raw))
                descriptors = [{"file": f"{key}.png", "source_box": box} for key, box in zip(keys, boxes)]
                cached = (images, descriptors)
                self._extracted_cache.put(extraction_key, cached, sum(image.width * image.height * 4 for image in raw))
            images, descriptors = cached
        else:
            images, descriptors = cached
        if stage == "extract":
            frames = {f"{key}.png": image for key, image in images.items()}
            versions = {key: hashlib.sha256(image.tobytes() + str(image.size).encode()).hexdigest() for key, image in frames.items()}
            scale = 1.0
        else:
            processed = process_frames(CanvasSpec(cfg.size, cfg.anchor), filename, cfg.source_spec(filename)['process'], images, cache=self._render_cache)
            frames, scale, versions = processed.frames, processed.scale, processed.versions
        return RenderResult(cfg, images, frames, descriptors, scale, versions)
