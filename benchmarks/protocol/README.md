# Deterministic multi-round protocol receipt

This disclosed fixture demonstrates the controller's actual hill-climbing
shape without making a claim about model capability. A deterministic candidate
generator proposes five isolated integer improvements per round. The controller
selects one strict gain, starts the next round from that immutable incumbent,
and repeats for four rounds before the holdout boundary.

The recorded run evaluates 20 candidates and climbs `0 → 5 → 10 → 15 → 20`.
Every point and incumbent step in `results/report.svg` comes from the accompanying
hash-chained ledger and machine receipt.

Reproduce and replace the disclosed receipt from the repository root:

```bash
HILL_CLIMBER_DEMO_RESULTS_DIR="$PWD/benchmarks/protocol/results" \
  ./examples/demo.sh
```

This fixture validates search orchestration, reporting, promotion, and evidence
plumbing. The separate duration benchmark is the repository's real Codex run.
