"""Evaluator fixture that reports whether a caller-supplied env var reached it.

Used only to prove `--env KEY=VAL` is additive on top of the fixed
sanitized environment (HOME, PATH, HILL_CLIMBER_*, ...), without granting
candidates or evaluators the parent shell's full environment.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

value = int(Path("solution.txt").read_text(encoding="utf-8").strip())
probe = os.environ.get("HC_TEST_PROBE", "MISSING")
leaked = os.environ.get("HC_TEST_SECRET", "MISSING")
print(json.dumps({
    "score": float(value),
    "gates": {"parseable": True},
    "details": f"probe={probe} secret={leaked}",
}, separators=(",", ":")))
