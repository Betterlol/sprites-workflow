"""Compatibility imports; implementation lives in storage.files."""

from .storage.files import frame_changes, numbered_frames, read_image, replace_frames, write_json

__all__ = ["read_image", "write_json", "frame_changes", "replace_frames", "numbered_frames"]
