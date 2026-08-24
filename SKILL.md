---
name: hill-climber
description: Use when asked to automatically improve a clean Git repository by generating and grading multiple Codex SDK candidates with a private holdout, finite budgets, durable resume, and evidence-backed promotion.
---

# Hill Climber

Use `hill-climber` when the user has a measurable repository improvement goal
and wants the search executed automatically. Do not use it for subjective work
without an external scoring contract, dirty repositories, untrusted evaluator
commands, or tasks whose necessary edits cannot be bounded by mutable globs.

## Operating contract

The model generates candidates. The controller owns baseline measurement,
worktree isolation, mutable-path enforcement, evaluator execution, ranking,
budgets, one-time holdout promotion, application, evidence, and recovery.

Never let a candidate:

- see holdout code, data, expected outputs, or diagnostics;
- edit the evaluators or broaden its own mutable paths;
- decide whether its result should be kept;
- bypass a failed gate because its prose sounds convincing;
- commit, push, merge, deploy, or modify production state.

## Preflight

1. Run `hill-climber --version` and `codex login status`.
2. Require `git status --short` to be empty in the target repository.
3. Turn the user's goal into one concise `--task` and put detailed constraints
   in a versioned or separately preserved details file.
4. Define a deterministic development evaluator and a genuinely unseen
   holdout evaluator. Keep both outside all mutable paths; keep the holdout
   outside the repository whenever possible.
5. Require evaluator stdout to be exactly one JSON object with finite numeric
   `score`, boolean `gates`, and optional bounded `details`, `metrics`, and
   `feedback`. Feedback is a string or string array containing actionable
   development diagnostics, never holdout content.
6. Select the narrowest repository-relative `--mutable` globs that can solve
   the task.
7. Choose explicit wall, token, failure, plateau, target, and repeat budgets.
8. Prefer `--no-apply` for a user's first experiment or any uncertain task.

## Launch

```bash
hill-climber run \
  --workspace /absolute/path/to/repo \
  --task "<one measurable objective>" \
  --details-file /absolute/path/to/task.md \
  --eval "<development evaluator argv>" \
  --holdout-eval "<private evaluator argv>" \
  --mutable "src/**/*.py" \
  --candidates 5 \
  --rounds 1 \
  --out /absolute/path/to/experiment \
  --no-apply
```

Quote each evaluator as one shell-style argv string. Use absolute evaluator
paths. Repeat `--mutable` for multiple surfaces. Add `--setup` only for a
trusted, reproducible dependency command that does not reveal holdout content.
Evaluator, holdout-evaluator, and setup commands only see a fixed, minimal
environment (`HOME`, `PATH`, `HILL_CLIMBER_*`, ...) — never the parent shell's
full environment. Repeat `--env KEY=VAL` to add exactly the variables an
evaluator needs (for example a device flag or log level); nothing else
crosses that boundary.

## Supervision and recovery

- Read progress labels on stderr; use `--json` for exactly one machine response
  on stdout.
- Inspect durable state with
  `hill-climber status EXPERIMENT --json`.
- Inspect one candidate with
  `hill-climber inspect EXPERIMENT --candidate r01-c03 --json`.
- Open `EXPERIMENT/report.svg` for the graphical run summary; verify its hash
  against `receipt.report.sha256` before sharing it as evidence.
- Stop gracefully with `hill-climber stop EXPERIMENT --json`.
- After Ctrl-C or recoverable failure, execute the exact emitted
  `hill-climber resume EXPERIMENT` command. Do not delete evidence or manually
  rerun individual candidate/holdout graders.
- If holdout started but did not finish, accept the fail-closed retained result;
  never replay or reconstruct that holdout inside the same experiment.

## Acceptance gate

Accept a result only from the verified receipt, never from candidate text.
Require all of the following:

1. `status`/`inspect` verifies manifest, state, and ledger integrity.
2. The selected candidate has a strict development gain and all gates pass.
3. The one-time holdout verdict is `promoted`, with no regression or failed
   gate.
4. `applied` matches the user's requested `--apply`/`--no-apply` behavior.
5. The source diff stays entirely inside the declared mutable surface.
6. The receipt records candidate counts, usage, stop reason, evidence paths,
   and the generated `report.svg`; the controller response records the next
   action.
7. With `--no-apply`, a promoted run still contains `winner.patch` while the
   source checkout remains clean.

If the receipt says `retained`, `blocked`, `invalid`, `crashed`, or reports a
failed gate, explain the evidence and retain the source baseline. Do not turn a
failed experiment into a success narrative.

## Evaluator guidance

- Higher scores are better. Prefer behavioral pass fractions or other granular,
  deterministic measures over a binary score.
- Return concise actionable `feedback` when a human could diagnose more from
  the failure than its scalar score. Later rounds receive it together with the
  prior mechanism, hypothesis, metrics, and keep/reject verdict.
- Use paired seeds/repeats when evaluation is noisy.
- Put non-negotiable correctness, security, compatibility, or test-count
  conditions in boolean gates.
- Keep scoring code fixed for the entire experiment.
- For subjective artifacts, combine deterministic gates with a versioned LLM
  rubric, clean-context repeated judgments, human-label calibration, and a
  fresh promotion panel. Follow `docs/llm-judged-visuals.md`; never treat one
  model verdict as ground truth.
- A score is only as meaningful as its evaluator. Call out weak proxies and
  refuse promotion when the evaluator does not measure the stated goal.
- Treat `--max-tokens` and `--max-wall-seconds` as round-boundary stop
  thresholds: candidates already in flight can overshoot them. Use candidate
  count, round count, and per-candidate/evaluator timeouts as hard outer bounds.

For full flags and artifact details, read `README.md`. For security boundaries,
read `SECURITY.md`.
