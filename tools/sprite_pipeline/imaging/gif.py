"""GIF preview encoding with stable transparency and explicit frame disposal."""

from __future__ import annotations

import io
import struct

from PIL import Image


def _indexed_frame(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    transparent = alpha.point(lambda value: 255 if value < 128 else 0)
    rgb = rgba.convert("RGB")
    rgb.paste((0, 0, 0), (0, 0), transparent)
    quantized = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    indexed = quantized.point(lambda value: value + 1)
    indexed.paste(0, (0, 0), transparent)
    palette = (quantized.getpalette() or [])[:765]
    indexed.putpalette([0, 0, 0] + palette + [0] * (765 - len(palette)))
    indexed.info["transparency"] = 0
    return indexed


def encode_gif(images: list[Image.Image], durations: list[int], loop: int) -> bytes:
    """Encode display steps; GIF uses 256 colors, binary alpha and 10 ms ticks."""
    if not images or len(images) != len(durations):
        raise ValueError("GIF needs one duration for each frame")
    size = images[0].size
    if any(image.size != size for image in images):
        raise ValueError("GIF frames must use one canvas size")
    if any(type(duration) is not int or not 1 <= duration <= 655_350 for duration in durations):
        raise ValueError("GIF frame duration must be 1–655350 ms")
    if type(loop) is not int or not 0 <= loop <= 65_535:
        raise ValueError("GIF loop count is out of range")
    frames = [_indexed_frame(image) for image in images]
    ticks = [max(20, round(duration / 10) * 10) for duration in durations]
    options = {
        "format": "GIF",
        "save_all": True,
        "append_images": frames[1:],
        "duration": ticks,
        "disposal": 2,
        "transparency": 0,
        "optimize": False,
        "interlace": False,
    }
    # GIF's finite loop value counts repeats after the first pass. WebP's
    # value counts total passes; an absent GIF extension means one pass.
    if loop == 0:
        options["loop"] = 0
    elif loop > 1:
        options["loop"] = loop - 1
    output = io.BytesIO()
    try:
        frames[0].save(output, **options)
    except struct.error as error:
        raise ValueError(
            "GIF merged frame duration exceeds its limit; shorten repeated holds"
        ) from error
    return output.getvalue()
