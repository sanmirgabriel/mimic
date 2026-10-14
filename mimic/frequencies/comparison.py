"""Exact, unpooled contrasts, always qualified by the two sampling contexts."""
from fractions import Fraction

from mimic.frequencies.models import LIMITATIONS, PATTERN_IDS


def rational(value):
    return dict(numerator=value.numerator, denominator=value.denominator)


def compare(left, right):
    fields = ('grammar_version', 'extractor_version', 'sample_unit', 'unicode_version', 'year_max')
    differences = [name for name in fields if getattr(left.measurement, name) != getattr(right.measurement, name)]
    population = ('unknown' if left.source.population is None or right.source.population is None else
                  'same-declared-scope' if left.source.population == right.source.population else 'different-declared-scopes')
    warnings = list(LIMITATIONS) + [
        'Samples are never pooled. Distinct identities do not prove independence; overlap may exist.',
        'No significance test, causal conclusion, global prevalence or transfer to other populations is justified.',
        'Matching population labels do not establish representative or equivalent sampling; review methodology, period and coverage.',
    ]
    if left.source.sample_id == right.source.sample_id:
        warnings.append('Shared sample identifier: samples may overlap or be the same sample.')
    if left.sha256 == right.sha256:
        warnings.append('Identical dataset content: this is not independent evidence.')
    sampling_fields = ('category', 'methodology', 'collection_start', 'collection_end', 'population', 'geography', 'sector', 'coverage_evidence')
    sampling_differences = [name for name in sampling_fields if getattr(left.source, name) != getattr(right.source, name)]
    unknown_sampling = [name for name in sampling_fields if getattr(left.source, name) is None or getattr(right.source, name) is None]
    counts_left = {p.id: p.count for p in left.patterns}
    counts_right = {p.id: p.count for p in right.patterns}
    rows = []
    for pattern_id in PATTERN_IDS:
        a, b = counts_left.get(pattern_id), counts_right.get(pattern_id)
        rows.append(dict(id=pattern_id,
            left=None if a is None else dict(numerator=a, denominator=left.measurement.sample_size),
            right=None if b is None else dict(numerator=b, denominator=right.measurement.sample_size),
            right_minus_left=None if differences or a is None or b is None else rational(
                Fraction(b, right.measurement.sample_size) - Fraction(a, left.measurement.sample_size)),
            evidence='missing-or-suppressed' if a is None or b is None else 'reported-in-both'))
    return dict(left=left.evidence(), right=right.evidence(), compatible=not differences,
                incompatible_fields=differences, population_comparability=population,
                sampling_differences=sampling_differences, unknown_sampling_fields=unknown_sampling, patterns=rows, warnings=warnings)
