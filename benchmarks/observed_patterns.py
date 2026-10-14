"""Synthetic bounded-stream baseline; run python -m benchmarks.observed_patterns."""

import argparse
import json
import time
import tracemalloc

from mimic.application.observations import PatternAnalysisService, report_bytes


class SyntheticObservations:
    """A synthetic binary readline source with O(1) caller memory."""

    def __init__(self, count):
        self.remaining = count

    def readline(self, size):
        if not self.remaining:
            return b""
        index = self.remaining
        self.remaining -= 1
        word = "Caju" if index % 2 else "ACME"
        suffix = ("", "!", "2026", "123", "_2026", "_123")[(index // 2) % 6]
        record = (word + suffix + "\n").encode("ascii")
        if len(record) > size:
            raise ValueError("Synthetic record exceeds the requested read bound")
        return record


def measure(count):
    service = PatternAnalysisService()
    started = time.perf_counter()
    report = service.analyze(SyntheticObservations(count), authorized=True,
                             reference_year=2026, source_label="synthetic-benchmark")
    elapsed = time.perf_counter() - started
    tracemalloc.start()
    try:
        measured = service.analyze(SyntheticObservations(count), authorized=True,
                                   reference_year=2026, source_label="synthetic-benchmark")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert measured == report
    return dict(observations=report.sample_size, structures=len(report.patterns),
                input_bytes=report.bytes_read, output_bytes=len(report_bytes(report)),
                elapsed_seconds=elapsed, peak_python_bytes=peak,
                measurement="Time and allocation peak use separate runs; excludes caller input and total process RSS.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=int, choices=(10000, 100000), default=10000)
    args = parser.parse_args()
    print(json.dumps(measure(args.observations), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
