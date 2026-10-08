"""Reusable application layer: use cases shared by CLI, API, Web UI and jobs.

This package never depends on ``argparse``, ``sys.argv``, stdout/stderr, HTTP,
HTML, templating or any database. Adapters translate their input into a
:class:`GenerationRequest` and consume the streamed result; the application
owns source precedence, mutator/policy assembly and Generator construction.
"""

from mimic.ranking import RankingOptions, GenerationResult

from mimic.application.errors import ApplicationError, InvalidGenerationRequest
from mimic.application.generation import (
    GenerationPlanSummary,
    GenerationService,
    PreparedGeneration,
)
from mimic.application.requests import (
    GenerationLimits,
    GenerationRequest,
    MutationOptions,
    PolicyOptions,
    SourceOptions,
    IntelligenceOptions,
)

__all__ = [
    "ApplicationError",
    "InvalidGenerationRequest",
    "GenerationService",
    "PreparedGeneration",
    "GenerationPlanSummary",
    "GenerationRequest",
    "MutationOptions",
    "PolicyOptions",
    "GenerationLimits",
    "SourceOptions",
    "IntelligenceOptions",
    "RankingOptions",
    "GenerationResult",
]
