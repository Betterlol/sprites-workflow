"""Compatibility imports; implementation lives in storage.configuration."""
from .storage.configuration import inside, Config, load_config, source_fingerprint, config_from_data, OUTPUT_DIRS, IMAGE_SUFFIXES, PROJECT_PATHS, NAME, positive, integer, merge

__all__ = ['inside', 'Config', 'load_config', 'source_fingerprint', 'config_from_data', 'OUTPUT_DIRS', 'IMAGE_SUFFIXES', 'PROJECT_PATHS', 'NAME', 'positive', 'integer', 'merge']
