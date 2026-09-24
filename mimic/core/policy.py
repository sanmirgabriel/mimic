"""Password policy filter."""

from __future__ import annotations


class PasswordPolicy:
    """Filters candidate passwords against configurable constraints.

    Args:
        min_len: Minimum password length (inclusive).
        max_len: Maximum password length (inclusive).  ``0`` means no limit.
        require_upper: Require at least one uppercase letter.
        require_lower: Require at least one lowercase letter.
        require_digit: Require at least one digit.
        require_special: Require a non-alphanumeric codepoint, including whitespace.
            Character classes use Python Unicode str predicates.
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
        for name, value in (("min_len", min_len), ("max_len", max_len)):
            if type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be >= 0")
        if max_len and min_len > max_len:
            raise ValueError("min_len must be <= max_len when max_len is enabled")
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
        if self.require_upper and not any(ch.isupper() for ch in candidate):
            return False
        if self.require_lower and not any(ch.islower() for ch in candidate):
            return False
        if self.require_digit and not any(ch.isdigit() for ch in candidate):
            return False
        if self.require_special and not any(not ch.isalnum() for ch in candidate):
            return False
        return True
