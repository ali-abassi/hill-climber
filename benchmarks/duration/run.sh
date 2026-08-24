#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCHMARK="${ROOT}/benchmarks/duration"
RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hill-climber-duration.XXXXXX")"
SOURCE="${RUN_ROOT}/source"
EXPERIMENT="${HILL_CLIMBER_BENCHMARK_OUT:-${RUN_ROOT}/experiment}"

mkdir -p "${SOURCE}"
cp "${BENCHMARK}/subject/duration.py" "${SOURCE}/duration.py"
git -C "${SOURCE}" init -q
git -C "${SOURCE}" config user.name "Hill Climber Benchmark"
git -C "${SOURCE}" config user.email "benchmark@localhost"
git -C "${SOURCE}" add duration.py
git -C "${SOURCE}" commit -qm baseline

"${ROOT}/bin/hill-climber" run \
  --workspace "${SOURCE}" \
  --task "Make parse_duration strict and support compound durations" \
  --details-file "${BENCHMARK}/TASK.md" \
  --eval "python3 ${BENCHMARK}/evaluate.py development" \
  --holdout-eval "python3 ${BENCHMARK}/evaluate.py holdout" \
  --mutable duration.py \
  --candidates 5 \
  --rounds 1 \
  --target-score 1 \
  --max-tokens 1000000 \
  --out "${EXPERIMENT}" \
  --no-apply

printf 'benchmark artifacts: %s\n' "${EXPERIMENT}"
