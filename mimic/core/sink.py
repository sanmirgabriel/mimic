"""Output sinks: streaming write to stdout or file."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


class Sink:
    """Writes generated words to an output destination in a streaming fashion.

    Args:
        output_path: File path to write to.  When ``None``, writes to
            ``sys.stdout``.
    """

    def __init__(self, output_path: str | None = None) -> None:
        self.output_path = output_path

    def drain(self, words: Iterator[str]) -> int:
        """Consume *words* and write each one as a line.

        Returns:
            The total number of words written.
        """
        count = 0
        if self.output_path is None:
            for word in words:
                sys.stdout.write(word + "\n")
                count += 1
        else:
            path = Path(self.output_path)
            with path.open("w", encoding="utf-8") as fh:
                for word in words:
                    fh.write(word + "\n")
                    count += 1
            logger.info("Wrote %d candidates to %s", count, self.output_path)
        return count
