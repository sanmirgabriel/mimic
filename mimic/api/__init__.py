"""Optional HTTP adapter; import this package only with the web extra installed."""

from mimic.api.app import create_app

__all__ = ["create_app"]
