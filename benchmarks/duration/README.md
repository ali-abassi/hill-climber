# Disclosed duration-parser smoke benchmark

This benchmark answers a narrow question: can the shipped Hill Climber loop
improve an incomplete Python parser under a frozen development evaluator and
then reproduce the gain on cases the candidates did not receive?

It is a smoke benchmark, not a leaderboard or a claim about arbitrary
repositories.

## Reproduce the controller inputs

Requirements are the same as a real climb: Git, Node 18+, Python 3.9+, and a
Codex CLI session authenticated with ChatGPT.

```bash
./benchmarks/duration/run.sh
```

The runner copies `subject/duration.py` into a new temporary Git repository,
keeps the evaluator outside that repository, launches five real Codex
candidates, and uses `--no-apply`. Set `HILL_CLIMBER_BENCHMARK_OUT` to keep the
full experiment at a chosen path.

## Recorded run

Run: `hill-climber-duration-verified-20260824`

| Field | Receipt |
|---|---:|
| Model | `gpt-5.6-terra`, medium reasoning |
| Development | `14/19` baseline → `19/19` winner |
| Holdout | `4/12` baseline → `12/12` winner |
| Candidates | 5 evaluated, 1 kept, 4 rejected |
| Usage | 555,989 input + 8,774 output tokens |
| Wall time | 134.718 seconds |
| Source changed | no (`--no-apply`) |
| Terminal reason | `target_achieved` |

The committed `receipt.json`, `manifest.json`, and `events.jsonl` are the exact
controller artifacts. Their referenced hashes match the committed ledger,
manifest, report, and patch. The test suite reapplies `winner.patch` to the
untouched subject and verifies both development and holdout scores.

## Evidence boundary

- This is one run on one small synthetic task, on `darwin-arm64`, with one
  model/configuration and no repeated seeds.
- The holdout was outside the candidate repository during the run. It is
  intentionally disclosed here afterward for auditability, so it must not be
  reused as private evidence for a new performance claim.
- All five candidates reached the same development score; deterministic
  complexity and candidate-ID tie-breakers selected one for holdout.
- An earlier run was invalidated when the holdout fixture was found to contain
  an arithmetic error. The evaluator was corrected and the whole experiment
  rerun from a new untouched baseline. The invalid run is not counted.
- No comparison against AutoAgent, autoresearch, manual Codex, or another model
  was run.
