#!/usr/bin/env bash
set -euo pipefail

# Reproduce the disclosed iteration experiment: one-shot vs multi-round at an
# identical candidate budget of 16. Roughly 18 minutes and 6.5M tokens total.
#
# --min-gain 0.01 sits above the measured 1.1% baseline noise floor at this
# workload size while still admitting a 2% incremental step. Small steps have
# to be admissible or the multi-round arm cannot work by construction.
#
# --plateau-rounds 4 deliberately disables early stopping in arm B so the
# plateau in rounds 3 and 4 is recorded rather than hidden.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCHMARK="${ROOT}/benchmarks/iteration"
RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hill-climber-iteration.XXXXXX")"

SEED_REPO="${RUN_ROOT}/seed"
mkdir -p "${SEED_REPO}"
cp "${BENCHMARK}/subject/textstats.py" "${SEED_REPO}/textstats.py"
git -C "${SEED_REPO}" init -q
git -C "${SEED_REPO}" config user.name "Hill Climber Benchmark"
git -C "${SEED_REPO}" config user.email "benchmark@localhost"
git -C "${SEED_REPO}" add textstats.py
git -C "${SEED_REPO}" commit -qm baseline

TASK="Reduce the wall time of summarize in textstats.py without changing its results"
DETAILS="Edit only textstats.py. Standard library only. Correctness is a hard gate: summarize must return exactly the same 3-tuple for every input. Do not detect or special-case the evaluator workload; promotion uses a different seed and size."

run_arm() {
  local name="$1" candidates="$2" rounds="$3"
  local workspace="${RUN_ROOT}/${name}"
  git clone -q "${SEED_REPO}" "${workspace}"
  git -C "${workspace}" config user.name "Hill Climber Benchmark"
  git -C "${workspace}" config user.email "benchmark@localhost"
  printf '\n=== arm %s: %s candidates x %s rounds ===\n' "${name}" "${candidates}" "${rounds}"
  "${ROOT}/bin/hill-climber" run \
    --workspace "${workspace}" \
    --task "${TASK}" \
    --details "${DETAILS}" \
    --eval "python3 ${BENCHMARK}/evaluate.py development" \
    --holdout-eval "python3 ${BENCHMARK}/evaluate.py holdout" \
    --mutable textstats.py \
    --candidates "${candidates}" --rounds "${rounds}" --plateau-rounds 4 \
    --repeats 3 --holdout-repeats 3 --min-gain 0.01 \
    --generation-parallel 4 \
    --max-tokens 4000000 --max-wall-seconds 3000 \
    --out "${RUN_ROOT}/experiment-${name}" \
    --no-apply
}

run_arm "a-one-shot" 16 1
run_arm "b-multi-round" 4 4

printf '\nexperiment artifacts: %s\n' "${RUN_ROOT}"
