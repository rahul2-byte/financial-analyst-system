"""
Configuration package.

Note: The main configuration is now in app.config.settings.
This module re-exports for backward compatibility.
"""

from app.config import settings

__all__ = ["settings"]
