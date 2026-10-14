"""Bounded local observation analysis, isolated from generation/Job snapshots.

Only aggregate shapes survive analysis. Literal words, digits and separators
are never learned, hashed, logged or returned. Repeated records count as
observations; no secret-bearing dedup set is retained.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import BinaryIO
import unicodedata

from mimic.application.errors import ApplicationError


GRAMMAR_VERSION = "observed-shapes-v1"
SCHEMA_VERSION = "observed-patterns-v1"
EXTRACTOR_VERSION = "pattern-extractor-v1"
MAX_ARTIFACT_BYTES = 16 * 1024
SEPARATORS = "@!#_.-"
SHAPES = tuple(
    shape
    for word in ("WORD", "ACRONYM")
    for shape in (word, word + " + SPECIAL", *(word + middle + number
                         for middle in (" + ", " + SEPARATOR + ")
                         for number in ("YEAR", "DIGITS")))
)
EXTRACTION_RULES = (
    "UTF-8; optional leading BOM; LF/CRLF records; no whitespace trimming or normalization.",
    "WORD: Unicode letters with attached combining marks; at least one letter.",
    "ACRONYM: 2-12 uppercase letters (a spelling heuristic, not semantic inference); takes precedence over WORD.",
    "YEAR: exactly four ASCII digits in the recorded year_interval; takes precedence over DIGITS.",
    "DIGITS: one or more ASCII digits; suffix only, after a WORD or ACRONYM.",
    "SEPARATOR: exactly one character from @!#_.- between the word and numeric suffix; literal not retained.",
    "SPECIAL: exactly one trailing character from @!#_.- without a number; analysis only, not reusable.",
    "Controls, format characters, surrogates and Unicode line/paragraph separators are invalid records.",
    "Every valid nonempty record counts, including duplicates and unmatched shapes; no deduplication.",
)
_MESSAGES = {
    "authorization_required": "Explicit authorization is required before reading observations.",
    "invalid_source_label": "Source label must be a non-sensitive lowercase identifier of at most 64 characters.",
    "invalid_limits": "Observation limits must be positive integers within the documented ceilings.",
    "invalid_report": "A current, internally consistent aggregate analysis report is required.",
    "read_failed": "Cannot read the local observation source.",
    "not_regular_file": "Observation input must be a regular local file, without a symlink.",
    "byte_limit": "Observation input exceeds the byte limit; no report was returned.",
    "line_limit": "Observation input exceeds the record limit; no report was returned.",
    "line_too_long": "An observation exceeds the per-record byte limit; no report was returned.",
    "reuse_disabled": "Explicit opt-in is required for pattern reuse.",
    "invalid_options": "Reference year must be 1900-9999 or absent; minimum occurrences must be 1-100000.",
    "artifact_limit": "Aggregate artifact exceeds the 16 KiB limit.",
    "write_failed": "Cannot publish the aggregate artifact; an existing destination is never overwritten.",
    "artifact_directory": "Aggregate artifact directory is unavailable or exceeds 64 entries.",
}


class ObservationError(ApplicationError):
    """Fixed public code/message and optional line number, never input values."""

    def __init__(self, code: str, line_number: int | None = None):
        self.code = code
        self.line_number = line_number
        message = _MESSAGES[code]
        if line_number is not None:
            message += f" Record: {line_number}."
        super().__init__(message)


@dataclass(frozen=True)
class ObservationLimits:
    max_bytes: int = 64 * 1024 * 1024
    max_lines: int = 100_000
    max_line_bytes: int = 1024

    def __post_init__(self):
        ceilings = (64 * 1024 * 1024, 100_000, 4096)
        values = (self.max_bytes, self.max_lines, self.max_line_bytes)
        if any(type(value) is not int or not 1 <= value <= ceiling
               for value, ceiling in zip(values, ceilings)):
            raise ObservationError("invalid_limits")


@dataclass(frozen=True)
class ObservedPattern:
    structure: str
    count: int

    @property
    def id(self) -> str:
        return "observed-pattern." + self.structure.lower().replace(" + ", "-") + ".v1"

    @property
    def reusable(self) -> bool:
        return not self.structure.endswith(" + SPECIAL")


@dataclass(frozen=True)
class ObservationOptions:
    reference_year: int | None = None
    min_occurrences: int = 5

    def __post_init__(self):
        if (self.reference_year is not None and
                (type(self.reference_year) is not int or not 1900 <= self.reference_year <= 9999)):
            raise ObservationError("invalid_options")
        if type(self.min_occurrences) is not int or not 1 <= self.min_occurrences <= 100_000:
            raise ObservationError("invalid_options")

    @property
    def year_max(self) -> int:
        return self.reference_year if self.reference_year is not None else 2099


@dataclass(frozen=True)
class ObservationReport:
    source_label: str
    limits: ObservationLimits
    bytes_read: int
    line_count: int
    sample_size: int
    empty_count: int
    invalid_utf8_count: int
    invalid_unicode_count: int
    unmatched_count: int
    patterns: tuple[ObservedPattern, ...]
    options: ObservationOptions = field(default_factory=ObservationOptions)
    suppressed_count: int = 0
    suppressed_structure_count: int = 0
    grammar_version: str = GRAMMAR_VERSION
    unicode_version: str = unicodedata.unidata_version
    schema_version: str = SCHEMA_VERSION
    extractor_version: str = EXTRACTOR_VERSION

    @property
    def matched_count(self) -> int:
        return self.sample_size - self.unmatched_count

    def to_dict(self) -> dict:
        result = asdict(self)
        result["patterns"] = [dict(id=pattern.id, structure=pattern.structure,
            occurrences=pattern.count, relative_frequency=dict(numerator=pattern.count, denominator=self.sample_size),
            reusable=pattern.reusable) for pattern in self.patterns]
        result["matched_count"] = self.matched_count
        result["extraction_rules"] = list(EXTRACTION_RULES)
        result["duplicate_policy"] = "count-every-observation"
        result["unsupported_count"] = self.unmatched_count
        result["valid_line_count"] = self.sample_size
        result["rejected_line_count"] = self.invalid_utf8_count + self.invalid_unicode_count
        result["distinct_structure_count"] = len(self.patterns) + self.suppressed_structure_count
        result["visible_structure_count"] = len(self.patterns)
        result["year_interval"] = [1900, self.options.year_max]
        result["limitations"] = [
            "Structures and counts describe only the supplied sample, not population frequencies or password strength.",
            "Unmatched observations are unsupported by this grammar; no literal values or examples are retained.",
            "Aggregate counts may still be sensitive; disclosure remains an operator decision.",
        ]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ObservationReport":
        """Reject unknown/free-text fields; never render unvalidated JSON."""
        failed = False
        try:
            if type(data) is not dict or type(data.get("patterns")) is not list or len(data["patterns"]) > len(SHAPES):
                raise ValueError()
            names = ("source_label", "bytes_read", "line_count", "sample_size", "empty_count",
                     "invalid_utf8_count", "invalid_unicode_count", "unmatched_count", "suppressed_count",
                     "suppressed_structure_count", "grammar_version", "unicode_version", "schema_version", "extractor_version")
            report = cls(**{name: data[name] for name in names},
                limits=ObservationLimits(**data["limits"]), options=ObservationOptions(**data["options"]),
                patterns=tuple(ObservedPattern(row["structure"], row["occurrences"]) for row in data["patterns"]))
            _validate_report(report)
            # Canonical JSON also distinguishes booleans, floats and integers.
            if json.dumps(data, sort_keys=True, allow_nan=False) != json.dumps(report.to_dict(), sort_keys=True, allow_nan=False):
                raise ValueError()
        except (KeyError, TypeError, ValueError, ObservationError, OverflowError, RecursionError):
            failed = True
        if failed:
            raise ObservationError("invalid_report")
        return report


def _authorized(authorized: bool) -> None:
    if authorized is not True:
        raise ObservationError("authorization_required")


def _source_label(label: str) -> None:
    if not isinstance(label, str) or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", label) is None:
        raise ObservationError("invalid_source_label")


def _structure(text: str, year_max: int = 2099) -> str | None:
    """Exclusive classification: acronym before word; year before digits."""
    end = len(text)
    while end and "0" <= text[end - 1] <= "9":
        end -= 1
    digits = text[end:]
    word = text[:end]
    separator = bool(digits and word and word[-1] in SEPARATORS)
    if separator:
        word = word[:-1]
    special = bool(not digits and word and word[-1] in SEPARATORS)
    if special:
        word = word[:-1]
    letters = 0
    uppercase = True
    for character in word:
        if character.isalpha():
            letters += 1
            uppercase = uppercase and character.isupper()
        elif not (letters and unicodedata.category(character).startswith("M")):
            return None
    if not letters:
        return None
    kind = "ACRONYM" if uppercase and 2 <= letters <= 12 else "WORD"
    if not digits:
        return kind + " + SPECIAL" if special else kind
    number = "YEAR" if len(digits) == 4 and 1900 <= int(digits) <= year_max else "DIGITS"
    return kind + (" + SEPARATOR + " if separator else " + ") + number


def _readline(stream: BinaryIO, size: int) -> bytes:
    failed = False
    try:
        record = stream.readline(size)
    except Exception:
        failed = True
    # Raise outside the handler: no foreign exception (possibly containing
    # plaintext or paths) is attached as __context__ or __cause__.
    if failed:
        raise ObservationError("read_failed")
    if type(record) is not bytes or len(record) > size:
        del record
        raise ObservationError("read_failed")
    return record


class PatternAnalysisService:
    """Stateless, read-only application use case. No persistence or logging."""

    def analyze(self, stream: BinaryIO, *, authorized: bool = False,
                source_label: str = "local-observations",
                limits: ObservationLimits | None = None,
                reference_year: int | None = None, min_occurrences: int = 5) -> ObservationReport:
        _authorized(authorized)
        _source_label(source_label)
        options = ObservationOptions(reference_year, min_occurrences)
        limits = limits if limits is not None else ObservationLimits()
        if not isinstance(limits, ObservationLimits):
            raise ObservationError("invalid_limits")
        counts = dict.fromkeys(SHAPES, 0)
        total = lines = sample = empty = invalid_utf8 = invalid_unicode = unmatched = 0
        while True:
            # At most one bounded record (or one extra byte) is consumed to
            # distinguish exact-limit EOF from an oversized input.
            size = min(limits.max_line_bytes + 3, limits.max_bytes - total + 1)
            if lines == limits.max_lines:
                size = 1
            raw = _readline(stream, size)
            if not raw:
                break
            total += len(raw)
            lines += 1
            if total > limits.max_bytes:
                del raw
                raise ObservationError("byte_limit", lines)
            if lines > limits.max_lines:
                del raw
                raise ObservationError("line_limit", lines)
            if raw.endswith(b"\n"):
                raw = raw[:-1]
                if raw.endswith(b"\r"):
                    raw = raw[:-1]
            if len(raw) > limits.max_line_bytes:
                del raw
                raise ObservationError("line_too_long", lines)
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                invalid_utf8 += 1
                del raw
                continue
            del raw
            if lines == 1:
                text = text.removeprefix("\ufeff")
            if not text:
                empty += 1
                del text
                continue
            if any(unicodedata.category(char) in ("Cc", "Cf", "Cs", "Zl", "Zp") for char in text):
                invalid_unicode += 1
                del text
                continue
            sample += 1
            structure = _structure(text, options.year_max)
            if structure is None:
                unmatched += 1
            else:
                counts[structure] += 1
            del text
        return ObservationReport(source_label, limits, total, lines, sample, empty,
                                 invalid_utf8, invalid_unicode, unmatched,
                                 tuple(ObservedPattern(shape, count) for shape, count in counts.items() if count >= min_occurrences),
                                 options=options,
                                 suppressed_count=sum(count for count in counts.values() if 0 < count < min_occurrences),
                                 suppressed_structure_count=sum(1 for count in counts.values() if 0 < count < min_occurrences))

    def analyze_file(self, path: str | Path, *, authorized: bool = False,
                     source_label: str = "local-observations",
                     limits: ObservationLimits | None = None,
                     reference_year: int | None = None, min_occurrences: int = 5) -> ObservationReport:
        _authorized(authorized)
        _source_label(source_label)
        ObservationOptions(reference_year, min_occurrences)
        if limits is not None and not isinstance(limits, ObservationLimits):
            raise ObservationError("invalid_limits")
        descriptor = None
        failed = False
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):
                raise ObservationError("not_regular_file")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ObservationError("not_regular_file")
            stream = os.fdopen(descriptor, "rb")
            descriptor = None  # The stream now owns the descriptor.
            with stream:
                return self.analyze(stream, authorized=True, source_label=source_label, limits=limits,
                                    reference_year=reference_year, min_occurrences=min_occurrences)
        except ObservationError:
            raise
        except (OSError, ValueError, TypeError):
            failed = True
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if failed:
            raise ObservationError("read_failed")

    def prepare_reuse(self, report: ObservationReport, request, *, enabled: bool = False,
                      generation_service=None) -> "ObservedPatternReuse":
        """Explicit structural filter over the existing service, using new operands.

        No literal observation is available to copy into a GenerationRequest.
        Request operands, policies, caps, provenance and score-v1 remain under
        the operator's control. Unsupported observations are reported as counts.
        """
        if enabled is not True:
            raise ObservationError("reuse_disabled")
        _validate_report(report)
        if report.unicode_version != unicodedata.unidata_version:
            raise ObservationError("invalid_report")
        from mimic.application.generation import GenerationService

        service = generation_service if generation_service is not None else GenerationService()
        return ObservedPatternReuse(report, service.prepare(request))


def _validate_report(report: ObservationReport) -> None:
    if (not isinstance(report, ObservationReport) or report.grammar_version != GRAMMAR_VERSION
            or report.schema_version != SCHEMA_VERSION or report.extractor_version != EXTRACTOR_VERSION
            or not isinstance(report.limits, ObservationLimits)
            or not isinstance(report.options, ObservationOptions)
            or not isinstance(report.unicode_version, str)
            or re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}", report.unicode_version) is None
            or not isinstance(report.patterns, tuple)):
        raise ObservationError("invalid_report")
    _source_label(report.source_label)
    counters = (report.bytes_read, report.line_count, report.sample_size, report.empty_count,
                report.invalid_utf8_count, report.invalid_unicode_count, report.unmatched_count,
                report.suppressed_count, report.suppressed_structure_count)
    if any(type(value) is not int or value < 0 for value in counters):
        raise ObservationError("invalid_report")
    seen = set()
    for pattern in report.patterns:
        if (not isinstance(pattern, ObservedPattern) or pattern.structure not in SHAPES
                or pattern.structure in seen or type(pattern.count) is not int or pattern.count < report.options.min_occurrences):
            raise ObservationError("invalid_report")
        seen.add(pattern.structure)
    if (sum(p.count for p in report.patterns) + report.suppressed_count != report.matched_count
            or len(report.patterns) + report.suppressed_structure_count > len(SHAPES)
            or not report.suppressed_structure_count <= report.suppressed_count <= report.suppressed_structure_count * (report.options.min_occurrences - 1)
            or report.sample_size + report.empty_count + report.invalid_utf8_count + report.invalid_unicode_count != report.line_count
            or not 0 <= report.unmatched_count <= report.sample_size
            or report.line_count > report.limits.max_lines or report.bytes_read > report.limits.max_bytes
            or report.line_count > report.bytes_read or bool(report.line_count) != bool(report.bytes_read)
            or tuple(p.structure for p in report.patterns) != tuple(shape for shape in SHAPES if shape in seen)):
        raise ObservationError("invalid_report")


class ObservedPatternReuse:
    """Projection/filter, never a generator or an automatic Job submission."""

    def __init__(self, report: ObservationReport, prepared):
        self.report = report
        self.prepared = prepared
        self._shapes = frozenset(pattern.structure for pattern in report.patterns if pattern.reusable)

    @property
    def warnings(self) -> tuple[str, ...]:
        return (
            "Uses only newly supplied generation operands; observed literals are unavailable.",
            "Unmatched observations are unsupported; no shape is synthesized by another engine.",
            "SPECIAL suffix structures are analysis-only; suppressed structures are never reused.",
            "Existing caps and policy apply; structural support does not guarantee coverage.",
            "Filtering follows existing ranking/Top-K, so retained count may be below the budget and ranks may have gaps.",
        ) + self.prepared.warnings

    def iter_results(self) -> Iterator:
        for result in self.prepared.iter_results():
            if _structure(result.candidate.value, self.report.options.year_max) in self._shapes:
                yield result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def load_report(stream: BinaryIO) -> ObservationReport:
    """Bounded, strict JSON import; arbitrary text is never reflected."""
    failed = False
    error = None
    raw = bytearray()
    try:
        while len(raw) <= MAX_ARTIFACT_BYTES:
            size = MAX_ARTIFACT_BYTES + 1 - len(raw)
            piece = stream.read(size)
            if type(piece) is not bytes:
                del piece
                error = "invalid_report"
                break
            if len(piece) > size:
                del piece
                error = "artifact_limit"
                break
            if not piece:
                break
            raw.extend(piece)
            del piece
    except Exception:
        failed = True
    if failed:
        del raw
        raise ObservationError("read_failed")
    if error is not None:
        del raw
        raise ObservationError(error)
    if len(raw) > MAX_ARTIFACT_BYTES:
        del raw
        raise ObservationError("artifact_limit")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError):
        failed = True
    del raw
    if failed:
        raise ObservationError("invalid_report")
    return ObservationReport.from_dict(data)


def load_report_file(path: str | Path) -> ObservationReport:
    descriptor = None
    failed = False
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise ObservationError("not_regular_file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ObservationError("not_regular_file")
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        with stream:
            return load_report(stream)
    except ObservationError:
        raise
    except (OSError, ValueError, TypeError):
        failed = True
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if failed:
        raise ObservationError("read_failed")


def report_bytes(report: ObservationReport) -> bytes:
    _validate_report(report)
    payload = (json.dumps(report.to_dict(), ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode("ascii")
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise ObservationError("artifact_limit")
    return payload


def save_report(report: ObservationReport, path: str | Path) -> None:
    """Publish a private complete artifact, atomically refusing existing paths."""
    payload = report_bytes(report)
    descriptor = staged = None
    failed = False
    try:
        descriptor, staged = tempfile.mkstemp(prefix=".mimic-patterns-", suffix=".part", dir=Path(path).absolute().parent)
        stream = os.fdopen(descriptor, "wb")
        descriptor = None
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, path)
    except (OSError, ValueError, TypeError):
        failed = True
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if staged is not None:
            Path(staged).unlink(missing_ok=True)
    if failed:
        raise ObservationError("write_failed")
