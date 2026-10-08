"""Bounded retention: scan everything, keep K; ties preserve encounter order."""
from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace
import heapq

from mimic.core.candidate import Candidate
from mimic.ranking.models import CandidateScore, GenerationResult


def select_top_k(candidates: Iterable[Candidate], budget: int,
                 scorer: Callable[[Candidate], CandidateScore]) -> Iterator[GenerationResult]:
    if type(budget) is not int or budget < 1:
        raise ValueError("budget must be a finite positive integer")
    heap: list[tuple[int, int, GenerationResult]] = []
    for index, candidate in enumerate(candidates):
        score = scorer(candidate)
        result = GenerationResult(candidate, score, encounter_index=index)
        entry = (score.total, -index, result)
        if len(heap) < budget:
            heapq.heappush(heap, entry)
        elif entry[:2] > heap[0][:2]:
            heapq.heapreplace(heap, entry)
    # Unique encounter indices keep Candidate and result objects out of comparisons.
    for rank, (_, _, result) in enumerate(sorted(heap, key=lambda entry: (-entry[0], -entry[1])), 1):
        yield replace(result, rank=rank)
