"""Environment configuration helpers for Lambda functions."""

from __future__ import annotations

import os

from .exceptions import ConfigurationError


def get_env(key: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and (value is None or value == ""):
        raise ConfigurationError(f"Environment variable {key} must be set")
    return value


def get_int_env(key: str, default: int | None = None, *, required: bool = False) -> int:
    value = os.getenv(key)
    if value is None:
        if required and default is None:
            raise ConfigurationError(f"Environment variable {key} must be set")
        if default is None:
            raise ConfigurationError(f"Environment variable {key} is missing and no default provided")
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {key} must be an integer") from exc


def get_float_env(key: str, default: float | None = None, *, required: bool = False) -> float:
    value = os.getenv(key)
    if value is None:
        if required and default is None:
            raise ConfigurationError(f"Environment variable {key} must be set")
        if default is None:
            raise ConfigurationError(f"Environment variable {key} is missing and no default provided")
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {key} must be numeric") from exc
