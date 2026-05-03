"""WTapi — Lightweight typed Python client for the Weblate REST API."""

from wtapi.client import WeblateBot, WeblateError, __version__

__all__ = ["WeblateBot", "WeblateError", "__version__"]
