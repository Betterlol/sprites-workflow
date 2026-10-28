"""Compatibility imports; implementation lives in storage.slices."""

from .storage.slices import extraction_fingerprint, read_slices, write_slices

__all__ = ["extraction_fingerprint", "read_slices", "write_slices"]
