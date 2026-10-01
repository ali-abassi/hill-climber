# Controller throughput benchmark

This measures the complete CLI/controller path using the existing fake Codex SDK and an external trusted evaluator. It makes no model calls. Each fresh temporary Git repository contains only `solution.txt`; five fixed candidates compete in one round with generation concurrency 2 and `--no-apply`. The deterministic winner scores 5. Only candidate development evaluations sleep; baseline and private holdout evaluations do not.

```sh
python3 benchmarks/controller/benchmark.py --root "$PWD" --repeats 3 --delay 1 --evaluation-parallel 5
```

The serial arm uses the controller's default evaluation concurrency. The parallel arm passes `--evaluation-parallel`. Runs alternate arm order, then emit one JSON document containing every raw measurement, medians, serial/parallel speedup, checkout commit and dirty state, and machine/runtime metadata. Timing includes CLI startup, worktrees, fake generation, evaluation, holdout verification, ledger writes, and report rendering.

To compare an older checkout lacking the concurrency flag, run this script against that checkout:

```sh
python3 benchmarks/controller/benchmark.py --root /path/to/baseline --serial-only --repeats 3 --delay 1
```

Every measured run must promote the expected winner, evaluate exactly five candidates, preserve the source repository, emit exactly one JSON document on stdout, and match the receipt's ledger/report SHA-256 hashes. Failure stops the benchmark. All experiment data is temporary and removed afterward; verified hashes remain in the JSON measurements. Save JSON only when explicitly requested with an artifact path outside the measured repository:

```sh
python3 benchmarks/controller/benchmark.py --root "$PWD" --output /tmp/hill-climber-controller.json
```

The sleeping evaluator is a synthetic I/O-bound workload. Speedup demonstrates overlap of independent waiting evaluators, with actual controller overhead included. It does not measure model quality, model latency, or CPU-bound evaluator performance. Keep delay, candidate count, generation concurrency, repeat count, machine, and runtimes identical when comparing checkouts. No generated benchmark results belong in this directory.
