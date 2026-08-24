# Disclosed latency smoke benchmark

This benchmark answers a narrow question: can the shipped Hill Climber loop
remove an asymptotic cost from a Python function, under a frozen development
evaluator with a hard correctness gate, and reproduce the speedup on a
workload the candidates never saw?

It is a smoke benchmark, not a leaderboard. One task, one model, one
configuration, one run. It does not establish a general success rate.

It exists because the other two disclosed benchmarks measure correctness
(`benchmarks/duration`) and protocol shape (`benchmarks/protocol`). Neither
shows a wall-time result, which is the most common reason to reach for this
tool.

## Setup

| Piece | Value |
|---|---|
| Subject | `subject/dedupe.py` — `find_duplicates` scanning a list with `any()` per record, so O(n²) |
| Score | Negative median wall seconds over 5 runs, because the controller maximizes score |
| Hard gate | `gates.correct` over 6 fixed cases. A faster function that returns different results scores `-1e9` |
| Development workload | 20,000 records, seed `20260824` |
| Holdout workload | 26,000 records, seed `76148291` — different size *and* different seed |
| Flags | `--candidates 5 --rounds 1 --repeats 3 --holdout-repeats 3 --min-gain 0.5 --no-apply` |

The evaluator, both workload generators, and the holdout seed live in this
directory, outside the repository under test. The workspace the candidates see
contains exactly one file: `dedupe.py`.

`--min-gain 0.5` was measured, not guessed. Four baseline runs on the
development workload gave medians of 5.077s, 4.964s, 4.916s, and 5.105s — a
spread of about 0.19s — so 0.5s sits clearly above the noise floor while a real
asymptotic fix clears it trivially.

## Result

| Phase | Baseline | Promoted | Speedup |
|---|---|---|---|
| Development (20,000 records) | 5.851s | 0.000769s | **7,611×** |
| Holdout (26,000 records, unseen) | 9.224s | 0.001106s | **8,342×** |

Five candidates, one kept, four rejected as lower-ranked, zero invalid, zero
crashed. 493,019 tokens, 361s wall. `promotion.holdout_independent` is `true`.

All five candidates passed the correctness gate, so the ranking was a genuine
choice among working implementations rather than a search for the only one that
did not break.

The promoted patch replaces the `any()` scan over a list with a set membership
test:

```diff
-    seen: list[dict] = []
+    seen: set[int] = set()
     duplicates: list[int] = []
     for record in records:
-        if any(previous["id"] == record["id"] for previous in seen):
-            duplicates.append(record["id"])
+        record_id = record["id"]
+        if record_id in seen:
+            duplicates.append(record_id)
         else:
-            seen.append(record)
+            seen.add(record_id)
```

## What the variance shows

The three development baseline repeats were 4.823s, 5.107s, and 7.624s. That
58% spread, on a loaded machine, is the reason this benchmark uses
`--repeats 3` and a measured `--min-gain` rather than the defaults. With
`--repeats 1` the repeat-robustness gate compares a single number against a
single number and carries no variance information at all. The effect is
invisible here because the real gain is four orders of magnitude, and it would
decide the outcome on a task with a 5% gain.

## Reproduce

```bash
./run.sh
```

Wall-clock seconds are machine-dependent, so
`test_disclosed_latency_benchmark_receipt_reproduces` does not re-assert the
numbers above. It applies the committed `results/winner.patch` to the untouched
subject and checks the two properties that must hold on any machine: the
correctness gate still passes in both phases, and the patched function is more
than 10× faster in both phases. It then verifies every SHA-256 in
`results/receipt.json` against the committed artifacts.
