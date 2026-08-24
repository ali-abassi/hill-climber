#!/usr/bin/env python3
"""Frozen deterministic evaluator for the disclosed latency smoke benchmark.

Two independent things are measured, and both matter:

* `gates.correct` -- the subject must still return exactly the right answer on
  fixed cases. A faster function that changes behaviour is not an improvement,
  so this is a hard gate rather than part of the score.
* `score` -- negative median wall seconds over a generated workload, because
  the controller maximizes score and we want lower latency.

Development and holdout use different generator seeds and different sizes, so
a candidate that special-cases the visible workload gains nothing on the
holdout. Nothing in this file, and no generated data, is written into the
repository under test.

Usage: evaluate.py PHASE [SCALE]

SCALE defaults to 1.0, which is what the disclosed run used. A smaller scale
shrinks only the timed workload so the committed receipt can be re-verified
cheaply; it never changes the correctness cases or the seeds.
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
import sys
import time
from pathlib import Path

PHASE_SEEDS = {"development": 20260824, "holdout": 76148291}
PHASE_SIZES = {"development": 20000, "holdout": 26000}
REPEATS = 5

# Fixed correctness cases, checked in both phases. Small and explicit so a
# failure is a real behaviour change rather than a timing artifact.
CORRECTNESS_CASES = (
    ([], []),
    ([{"id": 1, "name": "a"}], []),
    ([{"id": 1, "name": "a"}, {"id": 1, "name": "b"}], [1]),
    ([{"id": 3, "name": "a"}, {"id": 1, "name": "b"}, {"id": 3, "name": "c"}], [3]),
    (
        [{"id": 5, "name": "a"}, {"id": 5, "name": "b"}, {"id": 5, "name": "c"}],
        [5, 5],
    ),
    (
        [{"id": i % 4, "name": f"n{i}"} for i in range(10)],
        [0, 1, 2, 3, 0, 1],
    ),
)


def load_subject():
    spec = importlib.util.spec_from_file_location("dedupe", Path("dedupe.py").resolve())
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def build_workload(seed: int, size: int) -> list[dict]:
    rng = random.Random(seed)
    unique = int(size * 0.95)
    ids = list(range(unique)) + [rng.randrange(unique) for _ in range(size - unique)]
    rng.shuffle(ids)
    return [{"id": value, "name": f"record_{value:08d}"} for value in ids]


def main() -> None:
    phase = sys.argv[1]
    if phase not in PHASE_SEEDS:
        raise SystemExit(f"unknown phase: {phase}")
    scale = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    if not 0 < scale <= 1.0:
        raise SystemExit(f"scale must be in (0, 1]: {scale}")

    try:
        subject = load_subject()
        find_duplicates = subject.find_duplicates
    except Exception as error:  # noqa: BLE001 - report, never crash the climb
        print(json.dumps({
            "score": -1e9,
            "gates": {"importable": False, "correct": False},
            "details": f"subject import failed: {type(error).__name__}: {error}"[:400],
        }, separators=(",", ":")))
        return

    correct = True
    first_failure = ""
    for records, expected in CORRECTNESS_CASES:
        try:
            actual = find_duplicates([dict(item) for item in records])
        except Exception as error:  # noqa: BLE001
            correct = False
            first_failure = f"raised {type(error).__name__} on {records}"
            break
        if list(actual) != expected:
            correct = False
            first_failure = f"expected {expected} got {actual} for {records}"
            break

    if not correct:
        print(json.dumps({
            "score": -1e9,
            "gates": {"importable": True, "correct": False},
            "details": first_failure[:400],
            "feedback": [
                "Behaviour changed. find_duplicates must return each repeated id "
                "in the order the repeats occur, including one entry per repeat."
            ] if phase == "development" else [],
        }, separators=(",", ":")))
        return

    workload = build_workload(PHASE_SEEDS[phase], max(200, int(PHASE_SIZES[phase] * scale)))
    samples = []
    for _ in range(REPEATS):
        payload = [dict(item) for item in workload]
        started = time.perf_counter()
        find_duplicates(payload)
        samples.append(time.perf_counter() - started)
    median = statistics.median(samples)

    print(json.dumps({
        "score": -median,
        "gates": {"importable": True, "correct": True},
        "details": f"{phase} median {median:.6f}s over {REPEATS} runs of {len(workload)} records",
        "metrics": {
            "median_seconds": median,
            "min_seconds": min(samples),
            "max_seconds": max(samples),
            "records": len(workload),
        },
        "feedback": [
            "Latency is the score; correctness is a hard gate. Reduce the "
            "asymptotic cost of the duplicate check rather than tuning constants."
        ] if phase == "development" else [],
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
