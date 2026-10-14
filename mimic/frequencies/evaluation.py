"""Fixed synthetic ordering experiment. Never called by generation or Jobs.

Each opaque slot stands for a distinct synthetic candidate; its shape is declared,
not extracted from a secret. Repetitions in the holdout are observation weights.
No tuning, candidate production, scoring or plaintext holdout storage occurs.
"""
import hashlib
import json

from mimic.frequencies.comparison import rational
from mimic.frequencies.models import FrequencyError, PATTERN_IDS
from fractions import Fraction

# Frozen independently of imported counts and evaluation results.
UNIVERSE = tuple((f'slot-{index + 1:02}', pattern_id) for index, pattern_id in enumerate(PATTERN_IDS))
HOLDOUT = (0, 0, 2, 2, 2, 4, 4, 4, 6, 8, 8, 10)
FIXTURE_ID = 'synthetic-holdout-v1'
FIXTURE_UNICODE_VERSION = '15.1.0'  # Declared symbolic fixture contract; no runtime classifier.


def evaluate(reference):
    m = reference.measurement
    if (reference.source.category != 'synthetic' or reference.source.sample_id == FIXTURE_ID or
            m.sample_unit != 'observations' or m.year_max != 2099 or m.unicode_version != FIXTURE_UNICODE_VERSION):
        raise FrequencyError('evaluation')
    counts = {p.id: p.count for p in reference.patterns}
    baseline = list(range(len(UNIVERSE)))
    # Reported rows first, descending exact count (one common denominator),
    # then missing rows. Encounter index resolves every tie.
    experimental = sorted(baseline, key=lambda i: (UNIVERSE[i][1] not in counts, -counts.get(UNIVERSE[i][1], 0), i))
    fixture = dict(identity=FIXTURE_ID, universe=UNIVERSE, holdout_slot_indices=HOLDOUT,
                   budgets=(1, 3, 5, 12), year_max=2099, unicode_version=FIXTURE_UNICODE_VERSION)
    digest = hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()
    measurements = []
    for budget in fixture['budgets']:
        measurements.append(dict(budget=budget, holdout_observations=len(HOLDOUT),
            baseline_hits=sum(i in baseline[:budget] for i in HOLDOUT),
            experimental_hits=sum(i in experimental[:budget] for i in HOLDOUT),
            baseline=rational(Fraction(sum(i in baseline[:budget] for i in HOLDOUT), len(HOLDOUT))),
            experimental=rational(Fraction(sum(i in experimental[:budget] for i in HOLDOUT), len(HOLDOUT)))))
    return dict(method='synthetic-slot-coverage-v1', reference=reference.evidence(),
                holdout=dict(fixture, sha256=digest), baseline=[UNIVERSE[i][0] for i in baseline],
                experimental=[UNIVERSE[i][0] for i in experimental], coverage=measurements,
                limitations=[
                    'Opaque slots are the entire fixed synthetic candidate universe; they are not generated password strings.',
                    'Baseline is fixed grammar encounter order, not score-v1; experimental order is descending reported count, ties by encounter order.',
                    'Missing patterns follow all reported patterns, including explicit zeros; missing never means observed zero.',
                    'Reference and holdout must be independently constructed. Category/sample IDs are declarations, not proof of non-overlap.',
                    'The fixed holdout was not used to fit counts or tune this method. Do not tune against repeated holdout results.',
                    'Coverage is weighted synthetic observation coverage, not authentication success or a production ranking recommendation.',
                    'One candidate per shape excludes within-family uncertainty; this deliberately small experiment cannot justify production integration.',
                ])
