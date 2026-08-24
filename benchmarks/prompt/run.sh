#!/usr/bin/env bash
set -euo pipefail

# Reproduce the disclosed non-code prompt climb.
#
# Requirements:
#   - Codex logged in through the user's ChatGPT subscription
#   - BASETEN_API_KEY for the pinned DeepSeek Flash evaluator
#
# The climbed repository contains only prompt.md. The evaluator, development
# examples, and private holdout examples stay outside it.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCHMARK="${ROOT}/benchmarks/prompt"
RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hill-climber-prompt.XXXXXX")"
SOURCE="${RUN_ROOT}/source"
EXPERIMENT="${HILL_CLIMBER_BENCHMARK_OUT:-${RUN_ROOT}/experiment}"
: "${BASETEN_API_KEY:?BASETEN_API_KEY is required}"

mkdir -p "${SOURCE}"
cp "${BENCHMARK}/subject/prompt.md" "${SOURCE}/prompt.md"
git -C "${SOURCE}" init -q
git -C "${SOURCE}" config user.name "Hill Climber Benchmark"
git -C "${SOURCE}" config user.email "benchmark@localhost"
git -C "${SOURCE}" add prompt.md
git -C "${SOURCE}" commit -qm baseline

"${ROOT}/bin/hill-climber" run \
  --workspace "${SOURCE}" \
  --task "Improve prompt.md so it routes Acme support tickets accurately" \
  --details-file "${BENCHMARK}/TASK.md" \
  --eval "python3 ${BENCHMARK}/evaluate.py development" \
  --holdout-eval "python3 ${BENCHMARK}/evaluate.py holdout" \
  --env BASETEN_API_KEY \
  --mutable prompt.md \
  --candidates 5 --rounds 2 --plateau-rounds 1 \
  --repeats 3 --holdout-repeats 3 --min-gain 0.06 \
  --target-score 1.0 --generation-parallel 4 \
  --max-tokens 1800000 --max-wall-seconds 1800 \
  --out "${EXPERIMENT}" \
  --no-apply

printf 'benchmark artifacts: %s\n' "${EXPERIMENT}"
