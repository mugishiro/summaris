"""Custom exceptions shared across Lambda handlers."""

from __future__ import annotations


class ConfigurationError(RuntimeError):
    """Raised when required environment settings are missing or invalid."""


class ExternalServiceError(RuntimeError):
    """Raised when downstream services return recoverable errors."""
