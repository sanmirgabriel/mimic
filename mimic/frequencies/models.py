"""Bounded aggregate evidence. No password literals or classifier live here."""
from dataclasses import asdict, dataclass
from datetime import date
from fractions import Fraction
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

from mimic.application.observations import EXTRACTOR_VERSION, GRAMMAR_VERSION, ObservedPattern, SHAPES

SCHEMA_VERSION = 'frequency-knowledge-v1'
MAX_BYTES = 32 * 1024
MAX_COUNT = 2**63 - 1
PATTERN_IDS = tuple(ObservedPattern(shape, 0).id for shape in SHAPES)

_MESSAGES = {
    'schema': 'Invalid or unsupported aggregate frequency dataset.',
    'read': 'Aggregate source is unavailable, unsafe or exceeds the size limit.',
    'identity': 'Frequency identity must be a bounded lowercase id@version.',
    'registry': 'Frequency registry is unavailable, unsafe or exceeds 128 entries.',
    'integrity': 'Frequency dataset is missing, modified or corrupt.',
    'conflict': 'Frequency identity already contains different evidence.',
    'write': 'Cannot publish aggregate frequency evidence; no existing identity was overwritten.',
    'evaluation': 'Evaluation requires distinct synthetic reference and holdout samples with compatible extraction.',
}


class FrequencyError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(_MESSAGES[code])


def identity_parts(identity):
    if type(identity) is not str or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}@[a-z0-9][a-z0-9._-]{0,31}', identity):
        raise FrequencyError('identity')
    return tuple(identity.split('@'))


def _text(value, maximum=512, optional=False):
    if optional and value is None:
        return
    if (type(value) is not str or not value.strip() or len(value) > maximum or
            any(unicodedata.category(c).startswith('C') or c in '\u2028\u2029' for c in value)):
        raise FrequencyError('schema')


def _integer(value, low=0, high=MAX_COUNT):
    if type(value) is not int or not low <= value <= high:
        raise FrequencyError('schema')


def _url(value):
    if value is None:
        return
    _text(value, 512)
    failed = False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (not value.isascii() or any(c.isspace() for c in value) or '\\' in value or
                parsed.scheme != 'https' or not host or parsed.username is not None or
                parsed.password is not None or parsed.fragment or
                not re.fullmatch(r'[a-zA-Z0-9.-]+', host) or
                any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p) for p in host.split('.')) or
                parsed.port == 0 or re.search(r'%(?![0-9A-Fa-f]{2})', value) or
                re.search(r'%[01][0-9a-f]|%7f|%5c', value, re.I) or
                any(c in value for c in '<>"{}|^`')):
            failed = True
    except ValueError:
        failed = True
    if failed:
        raise FrequencyError('schema')


@dataclass(frozen=True)
class FrequencySource:
    title: str
    category: str
    methodology: str
    attribution: str
    license: str
    local_use_authorized: bool
    redistribution: str
    limitations: tuple[str, ...]
    sample_id: str
    reference_url: str | None = None
    collection_start: str | None = None
    collection_end: str | None = None
    population: str | None = None
    geography: str | None = None
    sector: str | None = None
    coverage_evidence: str | None = None

    def __post_init__(self):
        for name in ('title', 'methodology', 'attribution'):
            _text(getattr(self, name))
        if self.category not in ('synthetic', 'authorized-local', 'published-aggregate'):
            raise FrequencyError('schema')
        if self.local_use_authorized is not True or self.redistribution not in ('permitted', 'forbidden', 'unknown'):
            raise FrequencyError('schema')
        if self.license not in ('CC0-1.0', 'CC-BY-4.0', 'LicenseRef-Local', 'NOASSERTION'):
            raise FrequencyError('schema')
        if self.redistribution == 'permitted' and self.license not in ('CC0-1.0', 'CC-BY-4.0'):
            raise FrequencyError('schema')
        if type(self.limitations) is not tuple or not 1 <= len(self.limitations) <= 8:
            raise FrequencyError('schema')
        for item in self.limitations:
            _text(item)
        if type(self.sample_id) is not str or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', self.sample_id):
            raise FrequencyError('schema')
        _url(self.reference_url)
        for name in ('population', 'geography', 'sector', 'coverage_evidence'):
            _text(getattr(self, name), optional=True)
        if (self.geography is not None or self.sector is not None) and self.coverage_evidence is None:
            raise FrequencyError('schema')
        failed = False
        for value in (self.collection_start, self.collection_end):
            if value is None:
                continue
            try:
                if type(value) is not str or date.fromisoformat(value).isoformat() != value:
                    failed = True
            except (ValueError, TypeError):
                failed = True
        if failed or (self.collection_start and self.collection_end and self.collection_start > self.collection_end):
            raise FrequencyError('schema')


@dataclass(frozen=True)
class Measurement:
    sample_size: int
    sample_unit: str
    unicode_version: str
    year_max: int = 2099
    min_occurrences: int = 5
    grammar_version: str = GRAMMAR_VERSION
    extractor_version: str = EXTRACTOR_VERSION

    def __post_init__(self):
        _integer(self.sample_size, 5)
        _integer(self.min_occurrences, 5, MAX_COUNT)
        _integer(self.year_max, 1900, 9999)
        if self.sample_unit not in ('observations', 'unique-passwords'):
            raise FrequencyError('schema')
        if self.grammar_version != GRAMMAR_VERSION or self.extractor_version != EXTRACTOR_VERSION:
            raise FrequencyError('schema')
        if type(self.unicode_version) is not str or not re.fullmatch(r'[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}', self.unicode_version):
            raise FrequencyError('schema')


@dataclass(frozen=True)
class FrequencyRecord:
    id: str
    count: int

    def __post_init__(self):
        if self.id not in PATTERN_IDS:
            raise FrequencyError('schema')
        _integer(self.count)

    def ratio(self, measurement: Measurement) -> Fraction:
        if type(measurement) is not Measurement or self.count > measurement.sample_size:
            raise FrequencyError('schema')
        return Fraction(self.count, measurement.sample_size)


@dataclass(frozen=True)
class FrequencyDataset:
    dataset_id: str
    dataset_version: str
    source: FrequencySource
    measurement: Measurement
    patterns: tuple[FrequencyRecord, ...]
    metadata_non_sensitive: bool
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        if type(self.dataset_id) is not str or type(self.dataset_version) is not str:
            raise FrequencyError('schema')
        identity_parts(self.identity)
        if (type(self.source) is not FrequencySource or type(self.measurement) is not Measurement or
                self.schema_version != SCHEMA_VERSION or self.metadata_non_sensitive is not True or
                type(self.patterns) is not tuple or len(self.patterns) > len(PATTERN_IDS) or
                any(type(p) is not FrequencyRecord for p in self.patterns)):
            raise FrequencyError('schema')
        ids = tuple(p.id for p in self.patterns)
        if len(set(ids)) != len(ids):
            raise FrequencyError('schema')
        if any(p.count and p.count < self.measurement.min_occurrences for p in self.patterns):
            raise FrequencyError('schema')
        if sum(p.count for p in self.patterns) > self.measurement.sample_size:
            raise FrequencyError('schema')
        object.__setattr__(self, 'patterns', tuple(sorted(self.patterns, key=lambda p: PATTERN_IDS.index(p.id))))

    @property
    def identity(self):
        return self.dataset_id + '@' + self.dataset_version

    def to_dict(self):
        data = asdict(self)
        data['source']['limitations'] = list(self.source.limitations)
        data['patterns'] = [asdict(p) for p in self.patterns]
        return data

    @classmethod
    def from_dict(cls, data):
        failed = False
        try:
            data = dict(data) if type(data) is dict else None
            if data is None or 'schema_version' not in data:
                raise ValueError()
            source = data.pop('source')
            measurement = data.pop('measurement')
            patterns = data.pop('patterns')
            if type(source) is not dict or type(source.get('limitations')) is not list or type(measurement) is not dict or type(patterns) is not list or len(patterns) > 12:
                raise ValueError()
            if not {'sample_size', 'sample_unit', 'unicode_version', 'grammar_version', 'extractor_version', 'year_max', 'min_occurrences'} <= measurement.keys():
                raise ValueError()
            source = dict(source, limitations=tuple(source['limitations']))
            result = cls(source=FrequencySource(**source), measurement=Measurement(**measurement),
                         patterns=tuple(FrequencyRecord(**row) for row in patterns), **data)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
            failed = True
        if failed:
            raise FrequencyError('schema')
        return result

    @property
    def sha256(self):
        return hashlib.sha256(dataset_bytes(self)).hexdigest()

    def evidence(self):
        return dict(identity=self.identity, sha256=self.sha256, dataset=self.to_dict(),
                    frequencies=[dict(id=p.id, numerator=p.count, denominator=self.measurement.sample_size) for p in self.patterns],
                    warnings=list(LIMITATIONS))


LIMITATIONS = (
    'Counts describe the declared sample only; they are not authentication-success probabilities or universal prevalence.',
    'Missing patterns mean unavailable or suppressed evidence, never zero. Denominators include all declared observations.',
    'Suppression is not anonymity: repeated values, complementary totals and overlapping comparisons can disclose small cohorts.',
    'Metadata, authorization, attribution, licensing and sampling claims are operator declarations, not independently certified facts.',
)


def dataset_bytes(dataset):
    if type(dataset) is not FrequencyDataset:
        raise FrequencyError('schema')
    payload = (json.dumps(dataset.to_dict(), sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False) + '\n').encode('ascii')
    if len(payload) > MAX_BYTES:
        raise FrequencyError('schema')
    return payload


def from_observation(report, *, dataset_id, dataset_version, source, metadata_non_sensitive):
    """Bridge visible evidence only. Stricter knowledge threshold never unsuppresses."""
    from mimic.application.observations import ObservationReport
    report = ObservationReport.from_dict(report.to_dict())
    threshold = max(5, report.options.min_occurrences)
    return FrequencyDataset(dataset_id, dataset_version, source,
        Measurement(report.sample_size, 'observations', report.unicode_version, report.options.year_max, threshold),
        tuple(FrequencyRecord(p.id, p.count) for p in report.patterns if p.count >= threshold), metadata_non_sensitive)
