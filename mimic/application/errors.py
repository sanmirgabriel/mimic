"""Application-layer errors.

Deliberately shallow: use cases either succeed or raise
:class:`ApplicationError`. The layer never raises :class:`SystemExit` or any
transport-specific error -- adapters translate these into an exit code (CLI)
or an HTTP response (future API).
"""

from __future__ import annotations


class ApplicationError(Exception):
    """Base class for every error the application layer raises deliberately."""


class InvalidGenerationRequest(ApplicationError):
    """A :class:`~mimic.application.requests.GenerationRequest` is malformed.

    Raised for configuration that cannot produce a valid plan: unknown leet
    mode, non-positive limits, contradictory policy bounds, wrong operand
    types, or a context source that cannot be read/parsed.
    """
