"""Export mutations as hashcat .rule files instead of expanded wordlists."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Hashcat rule syntax reference:
#   l = lowercase, u = uppercase, c = capitalize, r = reverse
#   $X = append char X, ^X = prepend char X
#   sXY = replace X with Y

_LEET_RULES: list[str] = [
    "sa@",
    "se3",
    "si1",
    "so0",
    "ss$",
    "st7",
]


def export_rules(
    numbers: list[str],
    separators: str,
    leet_mode: str,
    output_path: str,
) -> int:
    """Write a hashcat-compatible .rule file.

    The generated rules replicate the same transformations that Mimic
    applies internally, allowing users to pair a small base wordlist with
    hashcat's rule engine for GPU-accelerated cracking.

    Args:
        numbers: Numeric suffixes/prefixes (years, PINs, etc.).
        separators: Separator characters.
        leet_mode: ``"none"``, ``"partial"``, or ``"full"``.
        output_path: Destination file path.

    Returns:
        Number of rules written.
    """
    rules: list[str] = []

    # Case rules
    rules.append(":")  # no-op (identity / original word)
    rules.append("l")  # lowercase
    rules.append("u")  # uppercase
    rules.append("c")  # capitalize

    # Reverse
    rules.append("r")

    # Leet rules
    if leet_mode == "full":
        rules.extend(_LEET_RULES)
    elif leet_mode == "partial":
        # Single substitutions only (hashcat applies one rule per line)
        for rule in _LEET_RULES:
            rules.append(rule)

    # Affix rules: append numbers
    for num in numbers:
        suffix_rule = "".join(f"${ch}" for ch in num)
        rules.append(suffix_rule)
        prefix_rule = "".join(f"^{ch}" for ch in reversed(num))
        rules.append(prefix_rule)

        # With separators
        for sep in separators:
            rules.append(f"${sep}" + "".join(f"${ch}" for ch in num))
            rules.append("".join(f"${ch}" for ch in num) + f"${sep}")

    path = Path(output_path)
    path.write_text("\n".join(rules) + "\n", encoding="utf-8")
    count = len(rules)
    logger.info("Wrote %d hashcat rules to %s", count, output_path)
    return count
