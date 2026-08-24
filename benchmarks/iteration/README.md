# Does iteration actually help? A disclosed controlled experiment

Every other disclosed run in this repository is single-round, and the only
multi-round evidence (`benchmarks/protocol`) uses a deterministic generator
rather than a model. So the premise the project is named after — that round
N+1 builds usefully on round N's incumbent with a real model — was never
tested.

This experiment tests it directly, holding the candidate budget constant and
varying only whether information flows between rounds.

| Arm | Configuration | Candidates |
|---|---|---|
| A — one-shot | `--candidates 16 --rounds 1` | 16 |
| B — multi-round | `--candidates 4 --rounds 4` | 16 |

Same model (`gpt-5.6-terra`, medium), same subject, same frozen evaluator, same
`--repeats 3 --holdout-repeats 3 --min-gain 0.01`, same `--no-apply`. The only
difference is iteration.

## Answer

**Iteration wins, significantly but modestly, and almost all of the value
arrives by round 2.**

Head-to-head re-measurement of both promoted patches, interleaved round-robin
to cancel machine drift, n=25 each, both verified to return identical output:

| Variant | Median | vs baseline |
|---|---|---|
| Baseline | 0.5123s | 1.00× |
| Hand-optimized reference | 0.1417s | 3.62× |
| Arm A winner (one-shot) | 0.1290s | 3.97× |
| **Arm B winner (multi-round)** | **0.1202s** | **4.26×** |

Arm B is **6.8% faster** than Arm A (Mann-Whitney U, n=25 per arm,
z=-4.67, **p=0.000003**). The distributions overlap on individual samples
because the machine was loaded, so the test is on ranks rather than on a
difference of two point estimates.

### The cost of that 6.8%

| Arm | Tokens | Wall | Result |
|---|---|---|---|
| A — one-shot | 2,390,195 | 436s | 3.97× |
| B — multi-round | 4,083,479 | 637s | 4.26× |

**+71% tokens and +46% wall time bought +6.8% result.** Whether that trade is
worth making depends entirely on whether 6.8% matters for the metric in
question.

### Where the value actually came from

Arm B's round-by-round trace:

| Round | Outcome | Score | Cumulative |
|---|---|---|---|
| 1 | kept `r01-c04` | -0.1325 | 3.87× |
| 2 | kept `r02-c02` | -0.1190 | 4.31× |
| 3 | retained — 3 × `repeat_regression`, 1 × `insufficient_gain` | — | plateau |
| 4 | retained — 3 × `repeat_regression`, 1 × `insufficient_gain` | — | plateau |

Round 1 captured about 90% of the total gain. Round 2 added 11%. Rounds 3 and 4
found nothing at all and consumed roughly half the arm's token budget for zero
improvement. **On this task `--rounds 2` was the efficient configuration, and
`--rounds 4` wasted about 2M tokens.**

The plateau was detected correctly rather than papered over: eight candidates
across rounds 3 and 4 were all rejected, six of them by the repeat-robustness
gate, and the controller retained the round-2 incumbent instead of promoting
noise.

### What iteration actually contributed

Both arms independently found the same four structural fixes. Their winning
patches differ in exactly one expression:

```python
# Arm A (one-shot)
total_vowels += sum(map(text.count, VOWELS))

# Arm B (multi-round, found in round 2 on top of round 1's incumbent)
total_vowels += (text.count("a") + text.count("e") + text.count("i")
                 + text.count("o") + text.count("u"))
```

Round 1 took the structural wins; round 2 removed the `sum()` and `map()`
call overhead from the hot loop. That is a textbook incremental refinement on
an existing incumbent, and it is the mechanism this project is built around,
observed working on a real model for the first time here.

### Both arms beat a careful human

The hand-optimized reference (`verify_task_suitability.py`, `fix_all`) reached
3.62×. Both arms beat it, because both noticed something the reference missed:
`initials` is only ever consumed by `len()`, so the string never needs to be
built at all — `initials_len += bool(text) + bool(words)` is enough. That
reference was written deliberately trying to be optimal.

## Task design, and why it took two attempts

An experiment about compounding is meaningless if one fix captures the whole
gain. `verify_task_suitability.py` measures each inefficiency in isolation and
refuses tasks where any single fix exceeds 60% of the achievable gain.

The first candidate task failed that check: an O(n²) duplicate scan mixed with
linear inefficiencies took **93.6%** of the gain by itself, because a quadratic
cost dominates linear ones at any real scale. It was rejected before any tokens
were spent.

The task used here keeps every inefficiency in the same asymptotic class:

| Fix | Share of achievable gain |
|---|---|
| Builtin vowel count instead of a character loop | 50.7% |
| Drop the `join`/`split` roundtrip | 22.5% |
| Lower-case once instead of three times | 5.5% |
| Accumulate list, join once, instead of `+=` | 4.2% |

No single fix dominates, and the parts sum to 82.9% while all four together
reach 100%, so the fixes compound rather than merely add. Ceiling: 3.76×.

Also worth recording: at 40,000 records the baseline measurement had a **35%**
spread between repeats; at 100,000 records it was **1.1%**. The workload was
sized for signal, and `--min-gain 0.01` sits above that 1.1% noise floor while
still permitting a 2% incremental step — small steps have to be admissible or
multi-round cannot work by construction.

## Honest limits

One task, one model, one pair of runs. This shows that iteration *can* add real
value on a compounding latency task; it does not establish how much it adds in
general, and it says nothing about tasks whose gains do not compound. The
plateau after round 2 may be a property of this task rather than of the method.

## Reproduce

```bash
python3 verify_task_suitability.py   # confirm the task still has the property
./run.sh                             # both arms, ~18 minutes, ~6.5M tokens
```

`test_disclosed_iteration_experiment_reproduces` verifies the committed
receipts: both arms promoted against an independent holdout, Arm B took its
gain across two rounds while Arm A used one, Arm B's promoted patch is the
faster of the two, and every SHA-256 in both receipts matches its artifact.
