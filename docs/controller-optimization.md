# Controller optimization — 2026-10-01

Ali requested a substantial optimization of `ali-abassi/hill-climber`. Work
started from upstream `67e54a3` in an isolated worktree; the older local checkout
and its uncommitted documents were preserved.

## Problems and decisions

| Observed problem | Change and reason |
|---|---|
| All development grading was serial, even for independent waiting evaluators | Opt-in `--evaluation-parallel` from 1 to 8. Default 1 protects timing metrics and shared resources; holdout stays serial. |
| Worktree checkout/removal blocked SDK and evaluator callbacks | Asynchronous Git worktree operations. Successful removal already clears registration, so skip redundant prune processes. |
| Every output chunk recopied everything collected so far | Store byte-bounded chunks and concatenate once. Preserve the 2 MiB limit on each stream and split UTF-8 sequences. |
| Fail-fast worker rejection released the writer lock while siblings were still running | Stop dequeueing and drain every started worker before checkpoint/lock release. |
| Resume read unverified artifacts and preferred generated data over a recorded grading failure | Reconcile generated/evaluated artifacts with the hash-chained ledger; failed evaluations remain terminal. |
| Resume reset a completed promotion, or rejected its own already applied patch | Restore the durable holdout decision; verify an applied source against the winner using a temporary index, preserving the user's index. Receipt-only recovery needs no model login or evaluator secrets. |
| Resume could start missing model turns despite a stop request or exhausted budget | Check recovery budgets before launching missing generation; finish already generated work when allowed. |
| Ungraded or malformed-response candidates disappeared from usage totals | Charge reported usage when generation completes, preserve failed-stream traces, and retain legacy accounting on older manifests. |
| First-round prompts lacked measured baseline diagnostics; truncation discarded recent evidence | Supply baseline feedback immediately and prioritize recent development decisions. No holdout diagnostics enter prompts. |
| Production dependency audit failed | Update the locked `brace-expansion` from 2.1.4 to 2.1.7; retain the pinned direct dependencies. |

No persistent evaluator cache was added: equal commits can produce different
results under noisy evaluators, and reusing a score without an explicit
determinism contract would weaken the experiment. No archive, distributed
workers, new service, or additional dependency was needed.

## Source survey and short steal-list

No external code was copied. The implementation mechanics were checked against
primary sources before adoption:

| Source | Verified mechanism | Decision |
|---|---|---|
| [Node serialization](https://github.com/nodejs/node/blob/a1074b84604d074cccd4796eff9f6e23cb648d4c/lib/internal/child_process/serialization.js), `advanced.parseChannelMessages` (MIT) | Accumulate chunks and track size; concatenate once a complete message is available. | Use the same general buffering principle, retaining this controller's existing output cap. Small local change. |
| [OpenEvolve evaluator](https://github.com/algorithmicsuperintelligence/openevolve/blob/1f8b7f102460edc8731826295aaacb11be5821d2/openevolve/evaluator.py), `Evaluator.__init__` (Apache-2.0) | Bounded evaluation task pool and dedicated executor with `parallel_evaluations`. | Add a bounded local grader pool, using the controller's existing worker mechanism. Keep metric-sensitive grading serial by default. |
| [autoresearch program](https://github.com/karpathy/autoresearch/blob/master/program.md) | Fixed evaluation, explicit keep/discard/crash evidence, and a simplicity criterion. | Preserve evidence-backed selection; avoid replacing the trusted finite controller with an indefinite prompt-owned loop. License endpoint returned 404 in this survey; no code reuse recommended. |
| [brace-expansion advisory](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr) | Vulnerable 2.x versions below 2.1.7 can perform quadratic parsing work. | Refresh the lockfile within the existing dependency range. |

Exa discovery request: `1108bb6af89ee003c3f2bc546fb984a9` ($0.007). Its Node
buffering result was followed to actual source; search excerpts were not used
as performance evidence.

## Measured throughput

The [benchmark](../benchmarks/controller) creates fresh temporary Git
repositories, generates five fixed candidates through the fake SDK, grades
them, verifies promotion, and renders the receipt/report. Candidate development
evaluators each wait 1.5 seconds; baseline and holdout do not wait. Every run
checks winner `r01-c02`, score 5, five evaluated candidates, unchanged source,
one JSON stdout document, and matching ledger/report hashes.

Three runs per arm on this Mac (Apple arm64, macOS 26.3.1, Node 26.8.1, Python
3.14.7, Git 2.46.0) produced these final committed-code measurements (`cdb6fc4`):

| Controller | Grading concurrency | Raw CLI wall seconds | Median |
|---|---:|---|---:|
| Upstream `67e54a3` | 1 | 10.642, 10.333, 10.363 | 10.363s |
| Optimized | 1 | 10.555, 10.170, 10.430 | 10.430s |
| Optimized | 5 | 4.066, 4.251, 4.032 | 4.066s |

The parallel arm is **2.55× faster than upstream**, reducing runtime by
**60.8%** for this synthetic I/O-bound task. Serial timing is within approximately 1% of upstream; no general serial
speedup is claimed from these three measurements.
This does not measure model quality, real Codex latency, CPU-bound grading, or
performance on arbitrary repositories. No model calls are made by this
benchmark. Evaluator commands are deliberately identical here; the receipt
labels holdout as dependent, and this benchmark makes no generalization claim.

Reproduce against a clean upstream checkout and the optimized checkout:

```sh
python3 benchmarks/controller/benchmark.py --root /path/to/upstream --serial-only --repeats 3 --delay 1.5 --output /tmp/controller-upstream.json
python3 benchmarks/controller/benchmark.py --root /path/to/optimized --repeats 3 --delay 1.5 --evaluation-parallel 5 --output /tmp/controller-optimized.json
```

JSON receipts include raw measurements, commit/dirty state, source-file hashes,
runtime metadata, and verification results. Keep generated experiments and
local benchmark output outside the repository.

## Acceptance and boundaries

Deterministic lifecycle tests cover parallel bounds and paired seeds, exact
Unicode capture, output overflow, descendant cleanup on timeout, all generated
usage, malformed SDK objects, completed holdout and post-apply recovery,
artifact tampering, worker draining, exhausted recovery budgets, terminal exit
codes, lock ownership, and legacy manifest compatibility. The original
controller and disclosed benchmark checks remain in the suite.

An independent Astra review reproduced post-apply, local-exclusion,
null-response, and concurrency-fixture gaps before they were fixed; focused
regressions cover them, and the final review passed the local-exclusion fix. Required
acceptance is `npm ci`, `npm run check`, and `npm audit --omit=dev`, plus the
Dogfood task receipt. GitHub CI must verify the pushed revision separately.

Graceful interruption and recorded failure recovery are tested. A hard kill
between ledger fsync and the state projection write still fails closed with
an evidence mismatch; no automatic reconstruction claim is made. This work
does not expand the existing local evaluator trust boundary or certify a new
real-model benchmark.
