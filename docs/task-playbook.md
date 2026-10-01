# Adapt the climb to the task

Hill Climber changes files; a protected evaluator decides whether the change
helped. The same loop can improve very different artifacts when their success
criteria are explicit. These six recipes describe evaluation plans, not shipped
universal graders or guarantees that a particular model will succeed.

Start with one objective, a clean repository, narrow mutable paths, three
candidates, one round, and `--no-apply`. Measure the baseline first. Increase the
budget only after the pilot reveals useful improvement rather than score gaming.
Keep evaluator code fixed throughout each experiment and holdout code/data
outside the repository. Never feed private diagnostics back into a new candidate.

## 1. Repair a parser without changing its interface

**Task:** “Support compound duration strings; retain strict rejection of malformed
input.” Mutable: `src/duration.py`. Preserve signature, units, and error types.

**Development:** 30 cases grouped by normalization, compound units, boundaries,
and malformed input. Score `passed / 30`. Gates require the existing compatibility
suite and protected assertion count to remain intact. Return failure categories
with observed behavior, rather than a list of answers to memorize.

**Holdout:** Different strings and combinations from the same behavioral contract,
including unseen nesting/spacing patterns. Development and holdout do not share
literal inputs. Use repeat 1 for a deterministic parser; `--min-gain 0` permits
only strict gains. A green gate alone is insufficient if the objective score
has no headroom.

**Mechanisms worth contrasting:** Tokenization, normalization before parsing,
and explicit grammar. Reject a branch keyed to visible input literals.

## 2. Make a hot path faster with identical outputs

**Task:** “Reduce median serialization latency while preserving byte-identical
results.” Mutable: `src/serialize.*`. Protect public interfaces and formats.

**Development:** Fixed paired workload seeds, warmup, multiple samples per case,
and a median inside the evaluator. Score `-median_ms`, so less latency gives a
higher score. Gates require exact outputs, correctness tests, and a defined
memory ceiling. Feedback reports slow workload categories and sample spread.

**Holdout:** Different payload sizes/shapes, on the same controlled machine and
runtime. Use `--repeats 3 --holdout-repeats 3 --evaluation-parallel 1`. If observed
baseline jitter is 0.4 ms, a justified pilot threshold might be
`--min-gain 1.0` (milliseconds in this score). Measure the actual noise first;
these numbers are examples. Neither overlapping graders nor shorter prompts
prove a speed gain in the artifact.

**Mechanisms:** Remove repeated conversion, batch allocations, or replace the
measured bottleneck. Preserve semantic gates even when the timing looks better.

## 3. Improve a reusable policy prompt

**Task:** “Route support tickets correctly under the approved policy, including
refund thresholds and security priority.” Mutable: `prompts/router.md`.

**Development:** 36 labeled cases with boundaries, ambiguous inputs, missing
amounts, multi-intent tickets, and instruction injection in ticket text. The
trusted evaluator pins model, effort, sampling, output schema, and policy labels.
Score exact task accuracy, not prompt length. Gates require valid output and
critical safety rules. Feedback says which rule or priority failed.

**Holdout:** Fresh phrasing and combinations, with threshold-adjacent cases from
the same policy. Pin the runtime and repeat stochastic evaluations; set
`--min-gain` above measured baseline variation. Do not infer missing business
policy from labels when the owner can provide the authoritative rule.

**Mechanisms:** Explicit precedence, tighter input trust boundary, or a clearer
abstention rule. Existing [prompt benchmark](../benchmarks/prompt/README.md)
contains a disclosed task-specific result and two rejected evaluator designs;
it is not evidence that the revised guidance improves every prompt.

## 4. Make a document useful to its reader

**Task:** “Rewrite the onboarding guide so a new user can finish setup without
inventing steps.” Mutable: `docs/onboarding.md`. Supply audience, prerequisites,
authoritative facts, required steps, and a word budget.

**Development:** Reader scenarios such as fresh install, missing prerequisite,
failed authorization, and upgrade. Combine mechanical link/required-step checks
with a pinned rubric for actionability, factual support, and sequence. Score a
weighted rubric normalized to 0–1; gates require every factual claim to have
support and every required step to exist. Brevity alone earns no score.

**Holdout:** Different user scenarios reviewed with the same rubric in a clean
context. Calibrate subjective scores against human judgments before trusting
promotion; repeat judges and use an independent panel. If calibration is absent,
report an exploratory proxy score and require human acceptance.

**Mechanisms:** Put prerequisites before actions, replace an ambiguous step with
an executable instruction, or remove an unsupported claim. More polished prose
must not hide a missing prerequisite.

## 5. Improve a file-backed interface

**Task:** “Make the pricing comparison readable and usable on mobile while
preserving purchase navigation.” Mutable: `web/pricing.html`, `web/pricing.css`.
Supply the visual direction and actual interactions; assets must already be
available locally or inside the allowed surface.

**Development:** Render at 1280 and 390 pixels, then exercise keyboard focus,
plan selection, and navigation. Gates check overflow, visible primary action,
contrast/accessibility requirements, and interaction completion. A versioned
visual rubric scores hierarchy, legibility, and fit to the brief on 0–1.
Evidence includes captures and observed interactions, not merely DOM validity.

**Holdout:** Other content lengths, viewports, and states; a fresh calibrated
panel judges without seeing generator identity or prior scores. A headless local
browser must be available to the trusted evaluator. Candidate generation cannot
fetch remote reference images or use an image service with its network disabled.
Without a working renderer or calibrated rubric, keep the visual claim bounded.

**Mechanisms:** Remove competing actions, repair responsive hierarchy, or improve
focus and error states. A static screenshot cannot certify the whole interaction.
See optional [visual evaluation guidance](llm-judged-visuals.md).

## 6. Tune configuration without compromising compatibility

**Task:** “Reduce worker startup failures across supported environments without
increasing resource limits.” Mutable: `config/worker.json`.

**Development:** Parse/schema checks plus representative environment scenarios.
Score `successful_scenarios / total_scenarios`; gates require valid keys,
compatibility, safe defaults, and fixed CPU/memory limits. Report the failing
constraint and environment category. Do not use a scalar that rewards simply
raising every limit.

**Holdout:** Unseen environment combinations and boundary workloads, evaluated
locally by trusted simulation or an isolated test runtime. Record simulation
limits; a passing local scenario does not prove production deployment behavior.
No account change, remote deploy, or production-data write is authorized by this
file experiment.

**Mechanisms:** Correct an incompatible option, reduce unnecessary concurrency,
or make a supported fallback explicit. Test the invalid configuration as a
negative control before search.

## Instructions and efficacy evidence

The candidate prompt is versioned in `scripts/hill_climber.mjs`. It begins with
`<purpose>`, keeps supplied content inside a data boundary, selects checks by
artifact, distinguishes baseline from later-round reflection, and asks for only
`mechanism`, `hypothesis`, and a summary of observed checks/limitations. The
controller still owns decisions and the output schema. XML tags organize text;
mutable enforcement and independent grading provide the executable boundary.

| Check | Cases or evidence | What it establishes |
|---|---|---|
| Input contract | 24 representative goals/details/feedback, across six artifact routes, missing details, Unicode, conflicting content, and hostile delimiters | Actual emitted prompt retains task data, separates supplied instructions, and delivers invariant boundaries |
| Lifecycle delivery | Fake SDK, two complete rounds, development feedback, private marker, independently scored result | Initial diagnostics and later reflection arrive without private holdout content; JSON/controller/apply boundaries remain intact |
| Domain quality | A frozen real model, evaluator, runtime, and 20–50 representative cases per intended route | Required before claiming better model behavior across domains; not established by deterministic tests |
| Efficiency | Same quality gates plus tokens, wall time, tool calls, and repeated unchanged checks versus prior prompt | Required before claiming the new instructions save usage/time; a shorter instruction is not sufficient |
| Subjective quality | Human-calibrated rubric, repeated clean judgments, fresh private promotion panel | Required before claiming writing or design quality rather than a proxy score |

Run the deterministic guidance checks with:

```bash
python3 -m unittest tests.test_candidate_guidance
```

They make no model calls. They verify the prompt contract and controller
integration, not a general success rate. Real-model validation must preserve
baseline and candidate prompts, pin the same runtime and cases, compare task
success with factual/schema/safety gates, and record usage and latency. Keep
rejected variants. If quality regresses or the evaluator is gamed, roll back the
prompt and revise the test contract rather than lowering its gates.
