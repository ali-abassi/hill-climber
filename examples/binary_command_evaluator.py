#!/usr/bin/env python3
"""Wrap a trusted command as a minimal binary codex-climb evaluator."""

from __future__ import annotations

import argparse
import json
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="trusted command, conventionally after --")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required")
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    passed = result.returncode == 0
    diagnostic = (result.stdout + result.stderr).strip()[-2000:]
    print(json.dumps({
        "score": 1.0 if passed else 0.0,
        "gates": {"command": passed},
        "details": diagnostic,
        "metrics": {"exit_code": result.returncode},
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
