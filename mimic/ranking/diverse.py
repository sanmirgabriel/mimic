"""Minimum family representation, then unchanged score priority. O(K + F).

The global K heap and at most F family winners suffice: removing winners from
the global heap leaves enough entries to fill K-F places. If N<K, retain N;
if K<F, take the K highest-priority winners. Final order remains score/encounter.
At most F-1 baseline entries are displaced when K>=F. Prefixes for different K
need not nest. Core's separate historical global dedup still requires O(N).
"""
from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace
import heapq

from mimic.core.candidate import Candidate
from mimic.ranking.families import FAMILY_VERSION, candidate_family
from mimic.ranking.models import CandidateScore, GenerationResult, Selection


def select_diverse(candidates: Iterable[Candidate], budget: int,
                   scorer: Callable[[Candidate], CandidateScore]) -> Iterator[GenerationResult]:
    if type(budget) is not int or budget < 1:
        raise ValueError("budget must be a finite positive integer")
    heap = []
    winners = {}
    for index, candidate in enumerate(candidates):
        score = scorer(candidate)
        family = candidate_family(candidate)
        result = GenerationResult(candidate, score, encounter_index=index)
        entry = (score.total, -index, result, family)
        if len(heap) < budget:
            heapq.heappush(heap, entry)
        elif entry[:2] > heap[0][:2]:
            heapq.heapreplace(heap, entry)
        previous = winners.get(family)
        if previous is None or entry[:2] > previous[:2]:
            winners[family] = entry
    priority = lambda entry: (-entry[0], -entry[1])
    representatives = sorted(winners.values(), key=priority)[:budget]
    selected = {entry[2].encounter_index: (entry, "family-representative") for entry in representatives}
    for entry in sorted(heap, key=priority):
        if len(selected) >= budget:
            break
        selected.setdefault(entry[2].encounter_index, (entry, "score-fill"))
    for rank, (entry, reason) in enumerate(sorted(selected.values(), key=lambda item: priority(item[0])), 1):
        yield replace(entry[2], rank=rank,
                      selection=Selection(entry[3], reason, FAMILY_VERSION))
