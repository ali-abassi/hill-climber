# GEPA source survey and steal-list

Surveyed on 2026-08-24 against source, tests, current activity, and licenses.
This is a clean-room design comparison; no external source code was copied.

## Ranked steal-list

### 1. Official GEPA: actionable feedback and candidate lineage — steal now

The MIT-licensed [GEPA engine](https://github.com/gepa-ai/gepa/tree/b265bf9ca77fd8e8d82039d9f74911b8780fe1ce)
is the authoritative implementation. Its reflective proposer evaluates a
parent on a minibatch, captures trajectories and evaluator feedback, asks a
reflection model to diagnose them, and records parentage for every accepted
candidate. Its state tracks the best candidates per validation instance or
objective rather than retaining only one aggregate winner.

**Port cost:** small for development feedback and lineage; large for a real
per-case Pareto archive. **Verdict:** preserve structured evaluator feedback,
candidate mechanism/hypothesis metadata, and prior decisions in later-round
prompts now. Require a versioned per-case/objective evaluator contract before
adding Pareto parent selection.

### 2. DSPy GEPA: feedback is part of the metric contract — steal now

The MIT-licensed [DSPy integration](https://github.com/stanfordnlp/dspy/blob/03641a2eeb53991a6b095561e146e19d0954edf1/dspy/teleprompt/gepa/gepa.py)
wraps the GEPA engine and makes textual feedback a first-class metric output.
It also exposes candidate parents, per-instance validation scores, objective
frontiers, evaluation counts, and resume logs.

**Port cost:** small. **Verdict:** accept bounded `feedback` from Hill Climber
evaluators and carry it into later rounds without allowing the model to grade
itself or see holdout evidence.

### 3. GEPA Viz: show the search tree, including failures — steal now

The MIT-licensed [GEPA Viz graph](https://github.com/modaic-ai/gepa-viz/blob/d4ee50570c7b46db432274a33b239c254bd5dced/client/packages/react/src/components/Graph.tsx)
draws accepted ancestry as solid edges and rejected proposals as smaller,
dashed branches. Candidate pages connect the prompt diff, reflection feedback,
and per-example results.

**Port cost:** small for static route edges; large for an interactive app.
**Verdict:** add parent-to-candidate route edges to the existing verified SVG.
Keep the report dependency-free, self-contained, and receipt-backed.

### 4. Skilled Proposer: generalize diagnoses instead of memorizing cases — steal the rule

The MIT-licensed [Skilled Proposer](https://github.com/cmpnd-ai/skilled-proposer/blob/2d55e9865ebcae042579714f75cb390440a64475/src/skilled_proposer/signatures.py)
uses an explicit diagnose → generalize → replace procedure and forbids literal
training-case lookup branches. It also bounds reflection context and output
length.

**Port cost:** tiny. **Verdict:** tell every candidate to convert visible
development failures into transferable mechanisms and preserve incumbent
strengths. Continue relying on the private holdout for actual overfit defense.

### 5. Hermes Agent Self-Evolution: useful product framing, avoid the implementation

[Hermes Agent Self-Evolution](https://github.com/NousResearch/hermes-agent-self-evolution/tree/0a929e3aa20e15cf04dc7c28492a7d41a5139125)
frames skills, prompts, tools, and code as evolvable surfaces and includes
train/validation/holdout splits plus structural constraints. At the inspected
revision, however, only skill evolution is marked implemented; its optimizer
call uses a stale `max_steps` argument, omits the currently required reflection
model, and its optimization metric is a keyword-overlap heuristic despite the
repository's richer judge class.

**Port cost:** not relevant. **Verdict:** retain the artifact-general framing;
do not depend on or copy this implementation.

## What the mature implementations converge on

- Keep scalar scores, but feed diagnostic traces and textual feedback to the
  proposer.
- Preserve the full candidate pool and explicit ancestry.
- Separate proposal, evaluation, acceptance, and visualization.
- Use bounded budgets, cached evaluations, durable state, and observable
  candidate events.
- Protect generalization with held-out evidence; an instruction saying “do not
  overfit” is guidance, not a promotion boundary.

## Changes carried into Hill Climber

1. Evaluators may return bounded `feedback` as a string or string array.
2. Aggregate candidate evidence retains per-repeat `metrics` and deduplicated
   feedback.
3. Later-round prompts receive candidate strategy, mechanism, hypothesis,
   selection verdict, score, diagnostics, feedback, and metrics from
   development only.
4. Prompts explicitly require a general diagnosis before mutation.
5. Reports draw every accepted and rejected route from its round incumbent.

## Deferred with an evidence requirement

True GEPA-style Pareto parent selection, crossover/merge, and component-level
mutation remain deferred. Hill Climber's evaluator currently has one trusted
primary score plus arbitrary informational metrics. A Pareto archive becomes
sound only after evaluators can declare stable per-case or named objective
scores, directions, identity hashes, and promotion semantics. Until then,
single-incumbent strict selection is easier to audit and harder to game.
