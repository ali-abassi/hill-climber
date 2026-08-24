# Codex hill-climb design notes

`hill-climber` is a clean-room implementation of a small experimental protocol,
not a port of another agent. The source survey was performed on 2026-08-24 and
used current repository code and documentation, not star counts alone.

## What the survey found

- [AutoAgent](https://github.com/thirdlayerinc/autoagent) has a strong written
  baseline → diagnose → one mechanism → benchmark → keep/discard discipline
  and communicates real kept/discarded experiments with a running-best graph.
  Its outer loop is still a prompt rather than an executable controller; the
  inspected source has no bounded resume state machine or implemented rollback
  controller.
- [autoresearch](https://github.com/karpathy/autoresearch) demonstrates a tiny
  mutable surface, a fixed evaluator, seeded measurements, a TSV experiment
  log, and simplicity bias. Its loop is also prompt-driven, sequential, and
  indefinitely adaptive against one visible validation set.
- [CORAL](https://github.com/Human-Agent-Society/Coral) supplies the strongest
  operational reference: independent worktrees, a manager/grader split,
  durable attempts, backpressure, and private grader isolation.
- [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)
  shows archive/diversity mechanisms and parallel evaluator workers. Those are
  useful for longer searches, but excessive for the first bounded local CLI.
- [Optuna](https://github.com/optuna/optuna) and
  [DVC Experiments](https://github.com/iterative/dvc) informed explicit trial
  states, stale-run recovery, immutable queued inputs, and isolated execution.
- [DeepSec](https://github.com/vercel-labs/deepsec) and
  [GitHub Next Rig](https://github.com/githubnext/rig) show robust Codex SDK
  streaming, usage capture, cancellation, and environment hygiene.
- [Tripwire](https://github.com/mornepousse/tripwire) reinforces the need for
  evaluator anti-weakening, captured failures, and test-count or assertion
  ratchets when the evaluator itself lives near agent-editable code.
- [GEPA](https://github.com/gepa-ai/gepa), its
  [DSPy integration](https://github.com/stanfordnlp/dspy), and
  [GEPA Viz](https://github.com/modaic-ai/gepa-viz) show the value of actionable
  evaluator feedback, explicit candidate lineage, per-instance Pareto memory,
  and accepted/rejected route visualization. The complete source-level
  [GEPA survey and steal-list](gepa-research.md) separates mechanics carried
  into this controller from features that require a stronger eval contract.

AutoAgent and autoresearch include MIT licenses at the inspected revisions. No
source was copied from either project.

## Decisions carried into `hill-climber`

| Survey lesson | Enforced mechanism |
|---|---|
| Start from a measured baseline | The untouched source commit is graded through the same development evaluator path. |
| Explore more than one idea | Five fresh Codex threads use distinct strategy lanes from one immutable incumbent. |
| Keep the editable surface narrow | Repository-relative mutable globs are checked against the committed diff; other authored paths invalidate the candidate. |
| Do not trust the agent to grade itself | The controller commits the candidate, removes its worktree, and grades the commit in a separate detached worktree. |
| Prevent adaptive holdout overfitting | Development evidence may feed later rounds; holdout runs once after search and is never replayed after interruption. |
| Roll back safely | Rejected worktrees are discarded; the user's source branch is never reset. Only a holdout-promoted patch is applied. |
| Make recovery mechanical | A frozen manifest, self-hashed state projection, fsynced hash-chained events, artifacts, and one-writer lock define the resume boundary. |
| Stop finitely | Round, failure, target, and plateau limits are controller-owned. Aggregate token and wall thresholds are checked between rounds and can be overshot by in-flight parallel candidates; per-candidate/evaluator timeouts remain hard. |
| Preserve subscription auth without leaking secrets | The SDK receives only an environment allowlist containing the cached ChatGPT login locations, not arbitrary API keys or CI secrets. |
| Prefer simpler equal solutions | Score, repeat floor, gates, changed-line count, then candidate ID determine a stable ranking. |
| Make progress inspectable | Every terminal run renders candidate scores and the round incumbent as a self-contained SVG backed by the same receipt and ledger. |
| Learn from more than a scalar | Bounded development feedback, metrics, candidate mechanisms, hypotheses, and keep/reject decisions are preserved and supplied to later rounds; holdout evidence never enters this channel. |
| Show experimental lineage | The report draws solid kept routes and dashed rejected routes from each round's immutable incumbent. |

## Intentionally deferred

Per-case Pareto parent selection, crossover, multi-island migration,
distributed workers, built-in LLM judges, cost estimation, and remote
sandboxes are not part of the current CLI. Pareto or merge selection requires
versioned per-case/objective scores and directions; arbitrary informational
metrics are not a sound substitute. The current runner exposes stable
experiment artifacts so those mechanisms can be added without putting control
flow back into a prompt.
