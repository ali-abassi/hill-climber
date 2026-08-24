from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


scenario = sys.argv[1]
phase = sys.argv[2]
if scenario == "mixed" and phase == "development" and os.environ.get("HILL_CLIMBER_CANDIDATE") == "r01-c03":
    print("first candidate evaluator diagnostic", file=sys.stderr)
    print("second deliberately long diagnostic line", file=sys.stderr)
    raise SystemExit(7)
if scenario == "slowholdout" and phase == "holdout":
    time.sleep(30)
value = int(Path("solution.txt").read_text(encoding="utf-8").strip())
score = float(value)
gates = {"parseable": True, "bounded": -1000 <= value <= 1000}

# This deliberately tempting development winner is invalid on private evidence.
if scenario == "cheater" and phase == "holdout" and value == 100:
    score = -100.0
    gates["not_overfit"] = False
else:
    gates["not_overfit"] = True

print(json.dumps({
    "score": score,
    "gates": gates,
    "details": f"{scenario}:{phase}:value={value}",
    "metrics": {"value": value},
}, separators=(",", ":")))
