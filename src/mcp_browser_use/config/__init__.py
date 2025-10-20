"""Configuration management for browser automation."""

from .environment import (
    get_env_config,
    profile_key,
    is_default_user_data_dir,
)

from .paths import (
    get_lock_dir,
    rendezvous_path,
    start_lock_dir,
    chromedriver_log_path,
    _lock_paths,
    _window_registry_path,
    _same_dir,
)

__all__ = [
    "get_env_config",
    "profile_key",
    "is_default_user_data_dir",
    "get_lock_dir",
    "rendezvous_path",
    "start_lock_dir",
    "chromedriver_log_path",
    "_lock_paths",
    "_window_registry_path",
    "_same_dir",
]
