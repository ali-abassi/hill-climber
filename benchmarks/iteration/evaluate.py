#!/usr/bin/env python3
"""Frozen evaluator for the multi-round vs one-shot experiment.

Score is negative median wall seconds (the controller maximizes score).
Correctness is a hard gate, so a faster function that returns different
results scores -1e9 rather than winning.

Feedback is deliberately neutral and identical in both experiment arms: it
reports the measured time and nothing about which inefficiencies remain.
Any advantage the multi-round arm shows must come from the controller
feeding back the incumbent's own code and score, not from hints written here.

Usage: evaluate.py PHASE [SCALE]
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
import sys
import time
from pathlib import Path

PHASE_SEEDS = {"development": 20260825, "holdout": 91773106}
PHASE_SIZES = {"development": 100000, "holdout": 130000}
REPEATS = 5
WORDS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
         "iota", "kappa", "lambda", "sigma"]

CORRECTNESS_CASES = (
    ([], (0, 0, 0)),
    ([{"text": "A"}], (1, 1, 2)),
    ([{"text": "HELLO WORLD"}], (3, 2, 2)),
    ([{"text": "aeiou AEIOU"}], (10, 2, 2)),
    ([{"text": "XYZ"}], (0, 1, 2)),
    ([{"text": "ONE TWO"}, {"text": "THREE FOUR"}], (7, 4, 4)),
)


def load_subject():
    spec = importlib.util.spec_from_file_location("textstats", Path("textstats.py").resolve())
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def workload(seed: int, size: int) -> list[dict]:
    rng = random.Random(seed)
    tags = [f"tag{i}" for i in range(12)]
    out = []
    for i in range(size):
        text = " ".join(rng.choice(WORDS) for _ in range(rng.randint(20, 40)))
        out.append({"id": i, "text": text.upper(), "tag": rng.choice(tags)})
    return out


def emit(payload: dict) -> None:
    print(json.dumps(payload, separators=(",", ":")))


def main() -> None:
    phase = sys.argv[1]
    if phase not in PHASE_SEEDS:
        raise SystemExit(f"unknown phase: {phase}")
    scale = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    if not 0 < scale <= 1.0:
        raise SystemExit(f"scale must be in (0, 1]: {scale}")

    try:
        summarize = load_subject().summarize
    except Exception as error:  # noqa: BLE001
        emit({"score": -1e9, "gates": {"importable": False, "correct": False},
              "details": f"import failed: {type(error).__name__}: {error}"[:300]})
        return

    for records, expected in CORRECTNESS_CASES:
        try:
            actual = summarize([dict(r) for r in records])
        except Exception as error:  # noqa: BLE001
            emit({"score": -1e9, "gates": {"importable": True, "correct": False},
                  "details": f"raised {type(error).__name__} on {records}"[:300]})
            return
        if tuple(actual) != expected:
            emit({"score": -1e9, "gates": {"importable": True, "correct": False},
                  "details": f"expected {expected} got {tuple(actual)} for {records}"[:300]})
            return

    size = max(1000, int(PHASE_SIZES[phase] * scale))
    data = workload(PHASE_SEEDS[phase], size)

    samples = []
    for _ in range(REPEATS):
        # Fresh dicts each repeat so nothing can be cached across repeats.
        payload = [dict(record) for record in data]
        started = time.perf_counter()
        summarize(payload)
        samples.append(time.perf_counter() - started)

    median = statistics.median(samples)
    emit({
        "score": -median,
        "gates": {"importable": True, "correct": True},
        "details": f"{phase} median {median:.6f}s over {REPEATS} runs of {size} records",
        "metrics": {"median_seconds": median, "min_seconds": min(samples),
                    "max_seconds": max(samples), "records": size},
        "feedback": [
            f"Median wall time is {median:.6f}s over {size} records. "
            f"Correctness is a hard gate and is currently passing."
        ] if phase == "development" else [],
    })


if __name__ == "__main__":
    main()
