#!/usr/bin/env python3
"""Measure controller throughput with fake generation and a sleeping evaluator."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


EVALUATOR = """import json, os, sys, time
from pathlib import Path
value = int(Path('solution.txt').read_text().strip())
if os.environ.get('HILL_CLIMBER_PHASE') == 'development' and value != 0:
    time.sleep(float(sys.argv[1]))
print(json.dumps({'score': value, 'gates': {'parseable': True, 'bounded': 0 <= value <= 5}}))
"""


def run(argv: list[str], **kwargs) -> str:
    return subprocess.run(argv, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def git(root: Path, *args: str) -> str:
    return run(["git", *args], cwd=root)


def measure(root: Path, delay: float, parallel: int | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="hill-climber-controller-") as raw:
        temporary = Path(raw).resolve()
        source = temporary / "source"
        source.mkdir()
        git(source, "init", "-q")
        git(source, "config", "user.name", "Benchmark")
        git(source, "config", "user.email", "benchmark@example.test")
        (source / "solution.txt").write_text("0\n", encoding="utf-8")
        git(source, "add", "solution.txt")
        git(source, "commit", "-qm", "benchmark baseline")
        baseline = git(source, "rev-parse", "HEAD")
        fake_bin = temporary / "bin"
        fake_bin.mkdir()
        codex = fake_bin / "codex"
        codex.write_text("#!/bin/sh\nprintf '%s\\n' 'Logged in using ChatGPT'\n", encoding="utf-8")
        codex.chmod(0o755)
        evaluator = temporary / "evaluate.py"
        evaluator.write_text(EVALUATOR, encoding="utf-8")
        evaluation = shlex.join([sys.executable, str(evaluator), str(delay)])
        experiment = temporary / "experiment"
        command = [sys.executable, str(root / "bin" / "hill-climber"), "run",
                   "--workspace", str(source), "--task", "Improve the deterministic integer score",
                   "--eval", evaluation, "--holdout-eval", evaluation,
                   "--mutable", "solution.txt", "--candidates", "5", "--rounds", "1",
                   "--generation-parallel", "2", "--no-apply", "--json", "--out", str(experiment)]
        if parallel is not None:
            command.extend(["--evaluation-parallel", str(parallel)])
        environment = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                       "HILL_CLIMBER_CODEX_MODULE": str(root / "tests/fixtures/fake_codex_sdk.mjs"),
                       "HILL_CLIMBER_FAKE_SCENARIO": "easy", "HILL_CLIMBER_FAKE_DELAY_MS": "0",
                       "NO_COLOR": "1"}
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=source, env=environment, text=True,
                                   capture_output=True, timeout=90 + 5 * delay)
        elapsed = time.perf_counter() - started
        if completed.returncode:
            raise RuntimeError(f"Controller exited {completed.returncode}: {completed.stderr}\n{completed.stdout}")
        if len(completed.stdout.strip().splitlines()) != 1:
            raise RuntimeError("Controller stdout must contain exactly one JSON document on one line")
        receipt = json.loads(completed.stdout)["result"]
        expected = {"candidates": 5, "crashed": 0, "invalid": 0, "kept": 1, "rejected": 4}
        if (receipt["status"] != "promoted" or receipt["incumbent"]["score"] != 5
                or receipt["incumbent"]["id"] != "r01-c02" or receipt["counts"] != expected
                or receipt["rounds_completed"] != 1 or receipt["applied"]):
            raise RuntimeError(f"Unexpected benchmark result: {receipt}")
        if (git(source, "rev-parse", "HEAD") != baseline or git(source, "status", "--porcelain")
                or (source / "solution.txt").read_text() != "0\n"):
            raise RuntimeError("--no-apply changed the source repository")
        hashes = {}
        for label, filename, claimed in (
            ("ledger", "events.jsonl", receipt["evidence"]["ledger"]["sha256"]),
            ("report", "report.svg", receipt["report"]["sha256"]),
        ):
            hashes[label] = hashlib.sha256((experiment / filename).read_bytes()).hexdigest()
            if hashes[label] != claimed:
                raise RuntimeError(f"Invalid {label} hash")
        return {"wall_seconds": elapsed, "controller_wall_seconds": receipt["wall_seconds"],
                "status": receipt["status"], "winner": receipt["incumbent"]["id"],
                "score": receipt["incumbent"]["score"], "counts": receipt["counts"],
                "source_unchanged": True, "json_stdout_verified": True, "sha256": hashes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Hill Climber checkout to measure")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0, help="candidate development evaluator sleep seconds")
    parser.add_argument("--evaluation-parallel", type=int, choices=range(1, 9), default=5)
    parser.add_argument("--serial-only", action="store_true", help="omit the new flag for older checkouts")
    parser.add_argument("--output", type=Path, help="optional JSON artifact path outside the measured checkout")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.repeats < 1 or not math.isfinite(args.delay) or not 0 <= args.delay <= 30:
        parser.error("repeats must be positive and delay must be finite, between 0 and 30")
    output = args.output.resolve() if args.output else None
    if output and (output == root or root in output.parents):
        parser.error("--output must be outside the measured checkout")
    metadata = {"root": str(root), "commit": git(root, "rev-parse", "HEAD"),
                "dirty": bool(git(root, "status", "--porcelain")),
                "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                  for name in ("scripts/hill_climber.mjs", "bin/hill-climber", "package-lock.json")},
                "platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
                "python": sys.version, "node": run(["node", "--version"]), "git": run(["git", "--version"]),
                "package_version": json.loads((root / "package.json").read_text())["version"]}
    measurements = {"serial": []}
    if not args.serial_only:
        measurements["parallel"] = []
    for repeat in range(args.repeats):
        arms = list(measurements)
        if repeat % 2:
            arms.reverse()
        for arm in arms:
            measurements[arm].append(measure(root, args.delay, None if arm == "serial" else args.evaluation_parallel))
    medians = {arm: statistics.median(item["wall_seconds"] for item in rows)
               for arm, rows in measurements.items()}
    result = {"schema": "hill-climber.controller-benchmark.v1", "metadata": metadata,
              "config": {"repeats": args.repeats, "delay_seconds": args.delay, "candidates": 5,
                         "rounds": 1, "generation_parallel": 2, "apply": False,
                         "evaluation_parallel": None if args.serial_only else args.evaluation_parallel},
              "measurements": measurements, "median_wall_seconds": medians}
    if "parallel" in medians:
        result["speedup"] = medians["serial"] / medians["parallel"]
    encoded = json.dumps(result, separators=(",", ":")) + "\n"
    if output:
        output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)


if __name__ == "__main__":
    main()
