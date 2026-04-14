"""Password policy filter."""

from __future__ import annotations

import re


class PasswordPolicy:
    """Filters candidate passwords against configurable constraints.

    Args:
        min_len: Minimum password length (inclusive).
        max_len: Maximum password length (inclusive).  ``0`` means no limit.
        require_upper: Require at least one uppercase letter.
        require_lower: Require at least one lowercase letter.
        require_digit: Require at least one digit.
        require_special: Require at least one non-alphanumeric character.
    """

    def __init__(
        self,
        min_len: int = 0,
        max_len: int = 0,
        require_upper: bool = False,
        require_lower: bool = False,
        require_digit: bool = False,
        require_special: bool = False,
    ) -> None:
        self.min_len = min_len
        self.max_len = max_len
        self.require_upper = require_upper
        self.require_lower = require_lower
        self.require_digit = require_digit
        self.require_special = require_special

    def accepts(self, candidate: str) -> bool:
        """Return ``True`` if *candidate* satisfies all configured rules."""
        length = len(candidate)
        if self.min_len and length < self.min_len:
            return False
        if self.max_len and length > self.max_len:
            return False
        if self.require_upper and not re.search(r"[A-Z]", candidate):
            return False
        if self.require_lower and not re.search(r"[a-z]", candidate):
            return False
        if self.require_digit and not re.search(r"\d", candidate):
            return False
        if self.require_special and not re.search(r"[^A-Za-z0-9]", candidate):
            return False
        return True
