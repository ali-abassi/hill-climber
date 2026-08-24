#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hill-climber-demo.XXXXXX")"
trap 'rm -rf "${DEMO_ROOT}"' EXIT

REPO="${DEMO_ROOT}/source"
EXPERIMENT="${DEMO_ROOT}/experiment"
FAKE_BIN="${DEMO_ROOT}/bin"
mkdir -p "${REPO}" "${FAKE_BIN}"

git -C "${REPO}" init -q
git -C "${REPO}" config user.name "Hill Climber Demo"
git -C "${REPO}" config user.email "demo@localhost"
printf '0\n' > "${REPO}/solution.txt"
git -C "${REPO}" add solution.txt
git -C "${REPO}" commit -qm baseline

printf '#!/bin/sh\nprintf "%%s\\n" "Logged in using ChatGPT"\n' > "${FAKE_BIN}/codex"
chmod +x "${FAKE_BIN}/codex"

RESULT_JSON="$(
  PATH="${FAKE_BIN}:${PATH}" \
  HILL_CLIMBER_CODEX_MODULE="${ROOT}/tests/fixtures/fake_codex_sdk.mjs" \
  HILL_CLIMBER_FAKE_SCENARIO="staircase" \
  "${ROOT}/bin/hill-climber" run \
    --workspace "${REPO}" \
    --task "Improve the deterministic demo score" \
    --details "Edit solution.txt to the best valid integer." \
    --eval "python3 ${ROOT}/tests/fixtures/evaluate_climb_fixture.py staircase development" \
    --holdout-eval "python3 ${ROOT}/tests/fixtures/evaluate_climb_fixture.py staircase holdout" \
    --mutable solution.txt \
    --candidates 5 \
    --rounds 4 \
    --plateau-rounds 4 \
    --out "${EXPERIMENT}" \
    --json --quiet
)"

if [[ -n "${HILL_CLIMBER_DEMO_REPORT:-}" ]]; then
  cp "${EXPERIMENT}/report.svg" "${HILL_CLIMBER_DEMO_REPORT}"
fi

if [[ -n "${HILL_CLIMBER_DEMO_RESULTS_DIR:-}" ]]; then
  mkdir -p "${HILL_CLIMBER_DEMO_RESULTS_DIR}"
  for artifact in events.jsonl manifest.json receipt.json report.svg winner.patch; do
    cp "${EXPERIMENT}/${artifact}" "${HILL_CLIMBER_DEMO_RESULTS_DIR}/${artifact}"
  done
fi

python3 -c '
import json, sys
r = json.load(sys.stdin)["result"]
print("Hill Climber demo")
print("status: {}".format(r["status"]))
print("candidates: {}".format(r["counts"]["candidates"]))
print("rounds: {}".format(r["rounds_completed"]))
print("baseline: {:g}".format(r["baseline"]["score"]))
print("final: {:g}".format(r["incumbent"]["score"]))
print("holdout: {}".format(r["promotion"]["verdict"]))
print("applied: {}".format("yes" if r["applied"] else "no"))
print("report: generated" if r.get("report", {}).get("format") == "image/svg+xml" else "report: missing")
' <<<"${RESULT_JSON}"
