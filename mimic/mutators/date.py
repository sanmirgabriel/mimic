"""Date-of-birth mutations: day/month/year digit combinations."""

from __future__ import annotations

import re
from collections.abc import Iterator

from mimic.mutators.base import Mutator

_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$")


class DateMutator(Mutator):
    """Expands a ``DD/MM`` or ``DD/MM/AAAA`` date into digit forms people
    actually type into passwords.

    Given ``"05/09/2000"`` it yields, in order:

    - ``"0509"``     -- day then month, both zero-padded
    - ``"0905"``     -- month then day, both zero-padded (day/month inverted)
    - ``"509"``      -- day unpadded + month padded
    - ``"905"``      -- month unpadded + day padded
    - ``"2000"``     -- year alone
    - ``"00"``       -- year, last two digits
    - ``"05092000"`` -- full date, day-month-year, all padded

    Given only ``"05/09"`` (no year), only the first four (year-independent)
    forms are yielded -- the year-dependent ones are simply skipped, no
    error.

    Duplicates (e.g. a date where day and month share the same digits) are
    dropped, preserving first-seen order.
    """

    def mutate(self, word: str) -> Iterator[str]:
        match = _DATE_RE.match(word.strip())
        if not match:
            raise ValueError(
                f"Invalid date format: {word!r} (expected DD/MM or DD/MM/AAAA)"
            )
        day_s, month_s, year_s = match.groups()
        day, month = int(day_s), int(month_s)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            raise ValueError(f"Invalid date value: {word!r}")

        dd, mm = f"{day:02d}", f"{month:02d}"
        d, m = str(day), str(month)

        tokens = [
            dd + mm,  # day, then month
            mm + dd,  # month, then day (day/month inverted)
            d + mm,
            m + dd,
        ]
        if year_s is not None:
            tokens.extend([year_s, year_s[-2:], dd + mm + year_s])

        seen: set[str] = set()
        for token in tokens:
            if token not in seen:
                seen.add(token)
                yield token
