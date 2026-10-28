"""Compatibility imports; implementation lives in storage.files."""
from .storage.files import read_image, write_json, frame_changes, replace_frames, numbered_frames

__all__ = ['read_image', 'write_json', 'frame_changes', 'replace_frames', 'numbered_frames']
