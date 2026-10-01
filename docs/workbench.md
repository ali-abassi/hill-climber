# A local workbench for measurable improvement

The user needs to define a useful goal, know what counts as improvement, run a
small experiment and understand whether its patch earned promotion. A controller
speedup does not solve the planning or interpretation problem. The new workbench
and adaptive skill address those parts directly.

## Decisions

- Keep one local interface with Plan, Results and Guide views. No account,
  cloud service, frontend framework or new dependency is needed.
- Treat six recipes as editable starting advice. They change examples, rubric
  guidance and repeat defaults; they do not invent an evaluator or assert quality.
- Start at three candidates and one round, with serial grading and no automatic
  application. Expand only after the evaluator detects known failures and pilot
  feedback demonstrates a useful mechanism. Thresholds are not strict cost caps.
- Prepare a quoted command for explicit terminal execution. A browser click
  cannot launch a real model run, execute user-supplied evaluator text, or apply
  a patch. Keep the existing controller as the trusted execution boundary.
- Read verified evidence, then match the ledger snapshot and receipt against the
  controller's state. Render candidate scores, hypotheses and feedback from that
  evidence. A live checkpoint can change during inspection; ask for refresh.
- Keep task instructions compact and operational. XML-delimited inputs cannot
  close instruction sections. This is prompt organization, not a security
  sandbox; enforcement still belongs to mutable-path checks and grading.
- Preserve the distinction between development progress, private promotion and
  source application. An uncalibrated subjective score is exploratory evidence.

## Source study and steal-list

Exa discovery on 2026-10-01 found the primary workbench/documentation below;
implementation references were inspected directly. No external source was copied.

| Mechanic | Source | Adaptation |
| --- | --- | --- |
| Trials and running-best history as navigable evidence | [Optuna dashboard GraphHistory.tsx](https://github.com/optuna/optuna-dashboard/blob/472069aa0115b7b3dd80a522f77848697c1e773d/optuna_dashboard/ts/components/GraphHistory.tsx), MIT | Small dependency-free candidate chart and explicit kept/rejected rows, rather than importing a large plotting framework. |
| Inspect objective, evaluations and reflections together | [GEPA Workbench](https://gepa-ai.github.io/gepa/workbench/) rendered reference | Keep result interpretation adjacent to candidate mechanisms and evaluator feedback. Do not add chat or let model prose claim a gain. |
| Distinguish rejected proposals from accepted candidates | [GEPA Viz run schema](https://github.com/modaic-ai/gepa-viz/tree/d4ee50570c7b46db432274a33b239c254bd5dced) | Use the existing ledger's candidate statuses. Preserve independent one-time holdout promotion instead of adding an adaptive private panel. |

## Verification and limits

`npm run check` covers command fidelity for all six recipes, invalid budgets and
paths, shell quoting, local origin/host rejection, request limits, a genuine
no-model demo, tampered receipts and state, plus existing controller lifecycle
checks. Guidance tests cover 24 representative normal, missing, Unicode and
conflicting inputs and actual two-round feedback delivery.

These tests establish working interfaces, evidence handling and instruction
delivery. They do not establish that every real model produces better artifacts
in every domain. The task playbook defines the frozen quality/efficiency
evaluation needed for that claim. Visual work needs local rendering tools and
assets; candidates have no network. The workbench currently prepares commands
and reads checkpoints; it does not manage live processes or automatically
author evaluator programs.
