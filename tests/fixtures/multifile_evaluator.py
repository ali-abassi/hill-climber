"""Evaluator whose score depends on two separate mutable files.

A single-file fixture cannot show that a candidate patch spanning several
files is applied, scored, and promoted as one unit, so this evaluator
requires both files to move for the score to improve.
"""
from __future__ import annotations

import json
from pathlib import Path

solution = int(Path("solution.txt").read_text(encoding="utf-8").strip())
helper = int(Path("helper.txt").read_text(encoding="utf-8").strip())
print(json.dumps({
    "score": float(solution + helper),
    "gates": {"parseable": True, "bounded": -1000 <= solution + helper <= 1000},
    "details": f"solution={solution} helper={helper}",
    "metrics": {"solution": solution, "helper": helper},
}, separators=(",", ":")))
