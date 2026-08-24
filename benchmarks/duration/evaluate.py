#!/usr/bin/env python3
"""Frozen deterministic evaluator for the disclosed duration smoke benchmark."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys


DEVELOPMENT = (
    ("0s", 0),
    ("7s", 7),
    ("2m", 120),
    ("1h", 3600),
    ("1h30m", 5400),
    ("2m10s", 130),
    ("1h2m3s", 3723),
    ("", ValueError),
    ("1", ValueError),
    ("1x", ValueError),
    ("1m1h", ValueError),
    ("1h2h", ValueError),
    (" 1s", ValueError),
    ("1s ", ValueError),
    ("-1s", ValueError),
    ("1.5h", ValueError),
    ("1H", ValueError),
    (None, ValueError),
    (1, ValueError),
)

HOLDOUT = (
    ("10h5s", 36005),
    ("12h34m56s", 45296),
    ("0h0m0s", 0),
    ("999h59m59s", 3599999),
    ("00h01m02s", 62),
    ("1h0s2m", ValueError),
    ("1m0m", ValueError),
    ("1s1m", ValueError),
    ("1 s", ValueError),
    ("+1s", ValueError),
    ("١s", ValueError),
    ([], ValueError),
)


def load_parser():
    path = Path("duration.py")
    spec = importlib.util.spec_from_file_location("duration_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("duration.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_duration


def passes(parser, value, expected) -> bool:
    try:
        result = parser(value)
    except Exception as error:  # The contract deliberately tests ValueError.
        return isinstance(expected, type) and error.__class__ is expected
    return not isinstance(expected, type) and type(result) is int and result == expected


phase = sys.argv[1]
cases = DEVELOPMENT if phase == "development" else HOLDOUT
try:
    parse_duration = load_parser()
    outcomes = [passes(parse_duration, value, expected) for value, expected in cases]
    import_gate = True
except Exception:
    outcomes = [False] * len(cases)
    import_gate = False

passed = sum(outcomes)
print(json.dumps({
    "score": passed / len(cases),
    "gates": {"imports": import_gate},
    "details": f"{phase}: {passed}/{len(cases)} cases passed",
    "metrics": {"passed": passed, "total": len(cases), "seed": os.environ.get("HILL_CLIMBER_SEED")},
}, separators=(",", ":")))
