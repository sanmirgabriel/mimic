"""Bounded, incremental local corpora with per-line provenance."""

from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

from mimic.core.candidate import Candidate, Origin
from mimic.core.seed import Seed


DEFAULT_MAX_LINES = 100_000
PTBR_CATEGORIES = ("football_teams", "reset_words", "common_terms", "cities")


def stream_dataset(
    path: str, *, ready: bool = False, max_lines: int = DEFAULT_MAX_LINES,
) -> Iterator[Seed]:
    """Yield normalized nonblank lines without loading the corpus into memory.

    The line limit applies to physical lines, including blanks. It is checked
    before reading the next line, so an oversized file fails explicitly.
    """
    if type(max_lines) is not int or max_lines < 1:
        raise ValueError("max_lines must be a positive integer")
    with Path(path).open(encoding="utf-8") as stream:
        for index, line in enumerate(stream, 1):
            if index > max_lines:
                raise ValueError(f"Dataset exceeds {max_lines} lines: {path}")
            value = line.strip()
            if value and not value.startswith("#"):
                source = "ready_candidate" if ready else "dataset"
                yield Seed(Candidate(value, (Origin(source, f"{path}:{index}", value),)),
                           combinable=False, mutable=not ready)


def stream_ptbr(categories: tuple[str, ...] = PTBR_CATEGORIES) -> Iterator[Seed]:
    root = files("mimic.data.ptbr")
    for category in categories:
        if category not in PTBR_CATEGORIES:
            raise ValueError(f"Unknown PT-BR category: {category}")
        with root.joinpath(f"{category}.txt").open("r", encoding="utf-8") as stream:
            for index, line in enumerate(stream, 1):
                value = line.strip()
                if value and not value.startswith("#"):
                    yield Seed(Candidate(value, (Origin("dataset", f"ptbr.{category}:{index}", value),)))
