---
name: hill-climber
description: Improve measurable file-backed artifacts—code, performance, prompts, writing, design, or configuration—through bounded Codex candidate experiments, fixed independent evaluation, private holdout verification, and inspectable evidence.
---

<purpose>
Turn a user's improvement goal into a small, trustworthy experiment. Adapt the
objective and checks to the artifact, run competing mechanisms, and accept only
an independently verified gain. The model proposes changes; the controller owns
isolation, evaluation, ranking, budgets, holdout, application, and recovery.
</purpose>

<when_to_use>
Use when the user wants repeated improvement of files in a clean Git repository
and an external evaluator can distinguish better from worse. Supported surfaces
include source code, prompts, documents, HTML/CSS/SVG, and configuration.

Use a direct edit for a known fix. Use research or human review first when the
goal has no credible scoring contract. An arbitrary website, image service,
production system, or account action is not automatically a file-backed task.
Do not run untrusted evaluators with the user's authority.
</when_to_use>

<define_the_experiment>
1. Inspect the artifact and its consumers. State the desired observable outcome,
   the things that must remain true, and the narrowest editable paths. Clarify
   only missing information that changes the objective or authorization.
2. Choose the route below. Translate “better” into one higher-is-better score and
   boolean gates. Use granular behavior scores where possible. Do not substitute
   brevity, keyword counts, or a flattering judge verdict for user success.
3. Prepare a fixed development evaluator and different, genuinely unseen holdout
   cases. Keep evaluators outside mutable paths; keep holdout code and data
   **outside the repository** because candidate worktrees copy the whole repo.
   Do not expose holdout through setup, prompts, or feedback. Reusing the same
   command records `holdout_independent: false`; it does not prove generalization.
4. Measure the untouched artifact before launching. Check score headroom,
   baseline failures, gate validity, runtime, and noise. Try a known broken
   artifact against the evaluator: it must lose or fail a gate. Fix a weak
   evaluator before search, then freeze it for that experiment.
5. Put the concise objective in `--task`; put audience, inputs/outputs, constraints,
   scoring meaning, and relevant local checks in `--details-file`. Include only
   development information. Do not put secrets or private cases there.
</define_the_experiment>

<task_routes>
| Artifact | Primary measure | Non-negotiable gates | Useful feedback |
|---|---|---|---|
| Code | Fraction of behavioral cases passed | Compatibility, security, protected test count | Failure classes and observed/expected behavior |
| Performance | Negative latency or normalized throughput | Equivalent outputs, correctness, resource ceiling | Measured bottleneck, variance, workload category |
| Prompts | Task success on labeled cases | Output schema, policy priority, grounded claims | Missing policy, boundary or injection failure |
| Writing | Anchored reader/task rubric | Factual support, required content, word budget | Unclear claim, missing evidence, unusable next action |
| File-backed design | Anchored visual/task rubric | Responsive layout, accessibility, functionality | Hierarchy, overflow, contrast, interaction failures |
| Configuration | Passing constraints or successful scenarios | Parse/schema validity, compatibility, safe defaults | Violated constraint, failing environment category |

Choose one route or a deliberate combined objective; do not add every check to
every task. Subjective writing/design scores need a versioned rubric, repeat
judgments, human calibration, and an independent promotion panel. If those are
missing, report a pilot proxy result and its limits rather than claiming quality.
</task_routes>

<runtime_contract>
Evaluator stdout must be exactly one JSON object:

```json
{"score":0.85,"gates":{"valid":true},"details":"17/20 cases passed","metrics":{"passed":17,"total":20},"feedback":["Compound units pass; whitespace normalization fails."]}
```

`score` is finite numeric, higher is better; `gates` contains booleans and every
gate must pass. `details`, `metrics`, and `feedback` are optional bounded
observations. Feedback names actionable development failure classes without
literal holdout answers. A failed evaluator is not a low-scoring valid result.

Candidate threads have workspace writes, no approvals, no web search, and
network disabled in SDK options. They may change only declared mutable paths;
never evaluator code/data, protected checks, Git metadata, or experiment evidence.
They do not decide what to keep, apply, commit, push, merge, or deploy.

Evaluator and setup programs run with the invoking user's authority: this is
**not an OS sandbox**. Use a container or VM for unknown code. Commands receive a
minimal environment. Inherit required variables explicitly with `--env KEY`;
never put secret values in command strings. Resume needs those keys rehydrated.
</runtime_contract>

<pilot_then_scale>
For interactive planning, run `hill-climber ui` and open the printed loopback
URL. Plan adapts evaluation advice to the task and prepares a quoted terminal
command; Results reads verified experiment evidence. The workbench makes no
real model calls. Its labelled demo uses fixed fixtures, not a model service.

Run `hill-climber --version`, `codex login status`, and `git status --short`.
Require a clean source checkout. Select an available Codex model deliberately
with `--model`; do not assume a historical default is available on the account.

Start with three candidates, one round, `--no-apply`, explicit limits, and a
small representative development panel. These are starting limits, not a promise
of enough tokens/time for every task:

```bash
hill-climber run \
  --workspace /absolute/path/to/repo \
  --task "<observable improvement while preserving named constraints>" \
  --details-file /absolute/path/to/task.md \
  --eval "python3 /absolute/evals/development.py" \
  --holdout-eval "python3 /absolute/private/holdout.py" \
  --mutable "<narrow repository-relative glob>" \
  --candidates 3 --rounds 1 --generation-parallel 2 \
  --candidate-timeout 600 --eval-timeout 120 \
  --max-wall-seconds 1800 --max-tokens 150000 --max-failures 2 \
  --out /absolute/path/to/experiment --no-apply
```

Quote evaluator argv as one argument; repeat `--mutable` for multiple surfaces.
Add trusted, reproducible `--setup` only when needed. Evaluator output must stay
outside the source checkout or be ignored, or the next run will fail `E_DIRTY`.

For deterministic correctness, one repeat can suffice. For timing, memory, or
stochastic judging, measure baseline variation, use `--repeats 3` and
`--holdout-repeats 3` or more, and set `--min-gain` above observed noise in the
score's units. With one repeat the repeat floor carries no variance information.

Keep `--evaluation-parallel 1` for timing, GPUs, shared state, and rate limits;
raise it to 2–8 only for independent development graders. Repeats within a grader
and final holdout remain sequential. Wall/token thresholds stop between rounds;
in-flight candidates can overshoot. Candidate count, round count, and individual
timeouts bound work more directly. Do not claim a strict aggregate cost cap.

Scale to five candidates and more rounds only when the pilot's feedback explains
real, generalizable gains and the measured budget is acceptable. Keep useful
changes, simplify equal alternatives, and vary mechanisms rather than paraphrase
the same approach. If score stalls, diagnose the evaluator, missing prerequisites,
or narrow editable surface before spending more. Do not tune against a disclosed
holdout: a new experiment after inspection needs fresh private cases.
</pilot_then_scale>

<inspect_and_recover>
Progress is append-only stderr; `--json` gives one machine response on stdout.
Use `hill-climber status EXPERIMENT --json` and
`hill-climber inspect EXPERIMENT --candidate r01-c03 --json` for verified evidence.
Open `EXPERIMENT/report.svg`; its hash is recorded in `receipt.report.sha256`.

Use `hill-climber stop EXPERIMENT --json` to stop. After interruption or a
recoverable failure, run the exact emitted resume command. Keep artifacts and
ledger intact. Never rerun a holdout manually: an interrupted holdout stays
closed; a completed holdout decision can resume application without regrading.
Tampered artifacts fail verification. Stopped/exhausted runs do not launch
missing model turns. SDK-reported generation usage is counted even for ungraded
or malformed turns; missing usage is not invented. Legacy runs retain their
original accounting mode.
</inspect_and_recover>

<accept_and_report>
Accept only a verified receipt showing strict development gain, passing gates,
and one-time holdout `promoted`. Check independent holdout status, source diff
within the mutable surface, counts, usage, stop reason, and evidence paths.
`applied` must match requested behavior. With `--no-apply`, a promoted run has
`winner.patch` and the source remains clean. A retained, blocked, invalid, or
crashed result keeps the baseline; explain the actual reason.

Report the observed baseline → selected score, private verdict, gate results,
application state, usage/runtime, and where to inspect the patch/report. State
what the evaluator measures and does not measure. Never treat candidate prose,
a help screen, or a synthetic demo as proof of real-model quality.

Stop when the requested experiment has a verified terminal result and concrete
handoff. Optional worked recipes and efficacy checks: `docs/task-playbook.md`.
Optional subjective visual calibration detail: `docs/llm-judged-visuals.md`.
</accept_and_report>

<completion_contract>
A generated candidate requires one completed metered turn, the exact declared
three-field metadata schema, and an unexpired/uninterrupted completion. Invalid
usage remains unknown; valid reported usage is counted even when a received
completion is rejected. Finite SDK streams that finish after ignoring abort are
drained for evidence, then refused before grading. This is acceptance protection,
not force termination of arbitrary third-party code. See docs/sdk-contract.md.
</completion_contract>
