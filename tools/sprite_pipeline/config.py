"""Compatibility imports; implementation lives in storage.configuration."""

from .storage.configuration import (
    IMAGE_SUFFIXES,
    NAME,
    OUTPUT_DIRS,
    PROJECT_PATHS,
    Config,
    config_from_data,
    inside,
    integer,
    load_config,
    merge,
    positive,
    source_fingerprint,
)

__all__ = [
    "inside",
    "Config",
    "load_config",
    "source_fingerprint",
    "config_from_data",
    "OUTPUT_DIRS",
    "IMAGE_SUFFIXES",
    "PROJECT_PATHS",
    "NAME",
    "positive",
    "integer",
    "merge",
]
