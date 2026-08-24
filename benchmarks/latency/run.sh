#!/usr/bin/env bash
set -euo pipefail

# Reproduce the disclosed latency smoke benchmark.
#
# The workspace under test contains only dedupe.py. The evaluator, its
# workload generator, and the holdout seed all live here, outside that
# repository, so no candidate can read the promotion evidence.
#
# --min-gain 0.5 is not arbitrary. Four baseline measurements on the
# development workload gave medians of 5.077s, 4.964s, 4.916s, and 5.105s, a
# spread of about 0.19s, so 0.5s sits well above the observed noise floor
# while remaining trivial for a real asymptotic fix to clear. --repeats 3 and
# --holdout-repeats 3 keep the repeat-robustness gate meaningful.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCHMARK="${ROOT}/benchmarks/latency"
RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hill-climber-latency.XXXXXX")"
SOURCE="${RUN_ROOT}/source"
EXPERIMENT="${HILL_CLIMBER_BENCHMARK_OUT:-${RUN_ROOT}/experiment}"

mkdir -p "${SOURCE}"
cp "${BENCHMARK}/subject/dedupe.py" "${SOURCE}/dedupe.py"
git -C "${SOURCE}" init -q
git -C "${SOURCE}" config user.name "Hill Climber Benchmark"
git -C "${SOURCE}" config user.email "benchmark@localhost"
git -C "${SOURCE}" add dedupe.py
git -C "${SOURCE}" commit -qm baseline

"${ROOT}/bin/hill-climber" run \
  --workspace "${SOURCE}" \
  --task "Reduce the wall time of find_duplicates in dedupe.py without changing its results" \
  --details-file "${BENCHMARK}/TASK.md" \
  --eval "python3 ${BENCHMARK}/evaluate.py development" \
  --holdout-eval "python3 ${BENCHMARK}/evaluate.py holdout" \
  --mutable dedupe.py \
  --candidates 5 \
  --rounds 1 \
  --repeats 3 \
  --holdout-repeats 3 \
  --min-gain 0.5 \
  --max-tokens 1000000 \
  --out "${EXPERIMENT}" \
  --no-apply

printf 'benchmark artifacts: %s\n' "${EXPERIMENT}"
