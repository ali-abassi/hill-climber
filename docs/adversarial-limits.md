# A skeptical self-climb

The earlier SDK-completion experiment reached its configured target in one
round. That proved a narrow contract, not that Hill Climber had reached a broad
quality ceiling. This follow-up challenged both the implementation and the
evaluator before expanding the search.

## First measured experiment

The frozen development panel contains 49 deterministic real-CLI cases across
candidate Git boundaries, unusual filenames, compatible whitespace, arbitrary
boolean gate names, finite score arithmetic, SDK failures, usage preservation,
capture limits, deadlines, and receipt consistency. The untouched source passed
13/49. A deliberately broken candidate passed 0/49 and failed the validity gate;
ordinary valid candidates were retained as controls. Original tracked checks
were hash-protected throughout the search.

Separate reviewers authored an unseen 50-case panel outside candidate
repositories. The trusted outer controller used it only after development
selection. Its results were not fed back into candidate generation.

| Stage | Result |
|---|---|
| Source | `0071cfe3bb054071077768e78e627c2f3ead6112` |
| Development progression | 13/49 → 22/49 → 29/49 → 36/49 |
| Actual search | 15 candidates, 3 rounds; 3 kept, 12 rejected |
| Configured ceiling | 5 candidates per round, up to 4 rounds |
| Stop | `token_budget_exhausted`, not a perfect score or plateau |
| Unseen comparison | 18/50 → 36/50; promoted with protected gates passing |
| Selected candidate | `r03-c03`, commit `da09ef598f0462e01a42d782b61afb4c212eabe4` |
| Integration | Byte-identical controller patch, commit `beef01e62981eaaee8bb6347eedc61f0fb295a88` |

Generation reported 14,536,899 input tokens, including 13,484,544 cached input
tokens, and 91,591 output tokens. The 12-million-token stopping threshold is
checked between rounds, so in-flight generation overshot it. This is measured
usage, not a strict spend limit. The receipt records 3,235.884 seconds of wall
time. The experiment used `--no-apply`; integration was an explicit host action.

The selected patch compares a candidate's complete final tree against its
immutable parent, uses controller-owned Git metadata and commits, disables Git
hooks and fsmonitor, handles machine-format rename records and literal arrow
filenames, accepts CRLF and trailing whitespace, keeps SDK errors fatal, retains
known usage once, and rejects inconsistent receipts during inspection and
terminal resume.

## Continued search and release checks

Thirteen development cases still failed after the first experiment. They cover
prototype-named gates, overflow-safe finite means and charts, bounded SDK trace
retention, and deadlines under finite microtask-heavy streams. Those known
failures remained visible and became the objective of a second experiment.
The development panel stayed frozen. Its private comparison uses newly authored,
withheld inputs; the first private panel is retired.

| Stage | Result |
|---|---|
| Source | `beef01e62981eaaee8bb6347eedc61f0fb295a88` |
| Development progression | 36/49 → 41/49 → 45/49 → 47/49 |
| Actual search | 9 candidates, 3 rounds; 3 kept, 6 rejected |
| Stop | `round_budget_exhausted`; no perfect-score target |
| Fresh unseen comparison | 8/25 → 21/25; promoted with protected gates passing |
| Private authorship | Host-authored, withheld; separate from the first panel's reviewers |
| Selected candidate | `r03-c03`, commit `8fbb51dca901505998c55e639a8e4951d58756bf` |
| Integration | Byte-identical controller patch, commit `1503aca` |

This run reported 8,254,545 input tokens, including 7,668,608 cached input tokens,
and 53,142 output tokens, over 2,177.559 seconds. It also used `--no-apply`.
The selected patch fixes extreme finite score means and chart geometry, preserves
prototype-named boolean gates, and bounds retained SDK traces to 2 MiB while
keeping received valid usage. Overall the two searches tested 24 candidates
across six actual improving rounds. Their private panels have different cases
and denominators; do not combine them into a single score.

## Separately tested direct fixes

Two public deadline cases still failed at the selected second winner. A small
direct fix checks monotonic elapsed time during and after finite SDK streams,
so a starved timer cannot admit an expired candidate. The final integrated
controller passes all 49 public cases, including preserved validity and
protected-check gates. That is public verification after a direct edit, not an
unseen score for the final source. Four of the 25 fresh unseen cases failed at
the selected experimental patch; they remain recorded, and the panel is retired.

Independent audits also reproduced three lifecycle problems outside that search
panel. Direct fixes bind the incumbent to ledger selection and evaluation before
private grading or application, stop through a writer-consumed request without
signalling a recycled lock PID, and recover a complete applied winner tree after
a crash before its application record. Recovery checks use an isolated index and
reject unrelated source edits without rerunning private grading.

An independent review caught a regression in the first stop fix: an existing
stop request interrupted resume and could consume the one-time comparison.
The corrected watcher distinguishes requests predating this resumed writer from
later requests. The existing flag still prevents new model turns. Permanent
tests use explicit checkpoints and delayed synthetic evaluation/private phases
to prove recovery, preservation of the winner, and exactly-once completion.

The original frozen search gate includes the 41 original Python tests. It does
not include the Node workbench tests. An independent Opus review caught a
workbench error-message regression that those search gates missed. The final
release must pass the complete `npm run check`, including Node tests and the new
adversarial regressions. Candidate gate success is not release acceptance.

## Source-informed choices

Git's documented porcelain `-z` format uses NUL-separated rename fields and
does not use the human-readable arrow delimiter. The implementation follows that
contract and verifies the whole final tree, including both sides of a rename.
Optuna's trial-validation flow informed the requirement to validate observations
before publishing a completed result. No optimizer framework or new dependency
was added. References and exact source revisions are recorded in the QA archive.

## What these results do not establish

- These are execution-contract checks, not a score for UI quality, universal
  optimization ability, or model output quality across task families.
- Candidate Git worktrees are not an OS sandbox. Withheld inputs were excluded
  from repositories and prompts, but local filesystem access is not a secrecy
  boundary against hostile candidate code.
- Receipt hashes detect inconsistency; they do not authenticate evidence against
  a writer who can rewrite every artifact and hash.
- Single repeats are appropriate to these deterministic fixtures. They provide
  no evidence about timing noise or stochastic evaluator robustness.
- Finished experiments retain absolute artifact paths. Moving or copying an
  experiment directory breaks receipt inspection until that path contract is
  deliberately redesigned.
- Provider allocations before SDK events reach the controller, indefinite
  uncooperative third-party execution, and crashes between a ledger append and
  its state checkpoint remain separate recovery/resource boundaries.

The local QA archive is
`~/dogfood/data/reviews/hill-limits-2026-10-02/`. It contains frozen evaluator
hashes, controls, source audits, original receipts, event ledgers, selected
patches, and charts. Generated experiments and private inputs are not committed
to this repository.
