# Changelog

## Unreleased

- Added `--env KEY=VAL` (repeatable) so setup, evaluator, and holdout-evaluator
  commands can receive exactly the extra environment variables they need.
  Still additive on top of the fixed sanitized environment; the parent
  shell's other variables never reach evaluators or candidate worktrees.
  Found via a 9-task live-repo test pass (real Codex-generated candidates,
  verified holdout speedups from 1.1x to 230x) that hit `KeyError` in an
  evaluator relying on an inherited env var.

## 0.4.0 — 2026-08-24

- Added bounded actionable evaluator feedback and preserved per-repeat metrics
  as development evidence for later rounds.
- Added reflective candidate memory containing strategy, mechanism,
  hypothesis, diagnostics, and keep/reject decisions without exposing holdout
  evidence.
- Added accepted and rejected lineage edges to every score report so the chart
  shows the actual routes attempted from each incumbent.
- Added a source-level GEPA/DSPy/GEPA Viz survey with an explicit steal-now,
  defer, and avoid decision record.

## 0.3.0 — 2026-08-24

- Replaced the one-jump README hero with a disclosed four-round protocol
  receipt that plots 20 candidates, four strict keeps, rejected routes, and the
  verified incumbent staircase from `0 → 5 → 10 → 15 → 20`.
- Added a calibrated LLM-judge contract for hill-climbing logos and other
  subjective artifacts without presenting a single model verdict as truth.
- Replaced the abstract route mark with a generated human rock-climber emblem,
  delivered as a real transparent PNG and validated on light and dark surfaces
  from 32 to 144 pixels.
- Rebuilt every generated run report around an empirical score trajectory:
  candidate results, round incumbents, selected patch, holdout verdict, usage,
  and application state.
- Added a disclosed real-Codex smoke benchmark with its frozen task, evaluator,
  manifest, hash-chained ledger, winner patch, receipt, and rendered report.
- Fixed `--no-apply` so promoted runs always save `winner.patch` while leaving
  the source checkout untouched.
- Documented the round-boundary token-budget overshoot and benchmark evidence
  limits instead of presenting them as stronger guarantees.

## 0.2.0 — 2026-08-24

- Renamed the project, repository, package, CLI, skill, schemas, and local state
  namespace to Hill Climber.
- Added an original two-color summit-route logo and a rendered GitHub hero that
  explains five-candidate selection and private-holdout promotion.
- Rebuilt the README around a verified quickstart, real receipts, progressive
  disclosure, honest alternatives, and explicit security boundaries.
- Added an automatic graphical `report.svg` to every completed experiment,
  including baseline-retained and holdout-reverted outcomes.

## 0.1.0 — 2026-08-24

- Initial standalone public release.
- Five isolated Codex SDK candidates per round with deterministic ranking.
- Detached development grading and one-time private-holdout promotion.
- Mutable-path enforcement, finite budgets, hash-chained evidence, durable
  resume, graceful stop, and apply-after-promotion behavior.
- ChatGPT subscription authentication through the cached Codex CLI session.
- Agent operating contract in `SKILL.md` and deterministic lifecycle suite.
