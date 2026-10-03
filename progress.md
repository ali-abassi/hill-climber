# Workbench progress

Implemented: local Plan/Results/Guide interface, six task recipes, no-apply
command handoff, downloadable briefs, verified candidate/patch inspection,
deterministic demo and adaptive instructions. Source review corrected integrity,
origin, parser, custom-budget, stale-response and mobile rendering issues.

Evidence: native checks cover controller lifecycle, 24 representative prompt
contract cases, two-round guidance delivery, six recipes through the actual CLI
parser, tampered receipt/state/patch, origins and subprocess-group timeout.
Desktop/mobile and feature verdicts live in Dogfood project
`hill-climber-workbench`; task `adaptive-workbench` is the acceptance authority.

Limits: no real-model cross-domain quality or efficiency claim. Browser UI
prepares commands and reads checkpoints; it does not manage real model runs,
author evaluators automatically or apply source changes.

## 2026-10-02 — Self-climb completion refinement

Implemented the holdout-promoted controller guard patch. Completion metadata now follows the declared exact schema; invalid metering cannot corrupt totals; valid reported usage and received evidence survive rejection; cancelled/expired finite completions cannot enter grading or promotion. Permanent synthetic regressions cover valid Unicode boundaries, schema failures, meter failures, expired responses, user cancellation, provider errors and evidence inspection.

Measured by the real self-climb: two candidates, one round, 11/26 to 26/26 development scenarios, and 5/20 to 20/20 independent private scenarios. Existing native lifecycle/recovery/performance gates pass throughout the experiment. Release validation uses npm ci, npm run check and npm audit --omit=dev; source-bound receipts and acceptance are recorded in Dogfood task self-climb-sdk-contract. The experiment chart and immutable artifacts remain in Dogfood's local review bundle.

This measures the completion contract, with finite synthetic SDK responses. It does not establish general model quality, force termination, OS containment, throughput or production readiness. Existing untracked user documents are preserved; account/global configuration and real sessions remain unchanged.

Separately added: HILL_CLIMBER_CODEX_PATH selects a compatible installed CLI for both login preflight and SDK turns. It replaces the need for the temporary SDK-module wrapper, keeps the default when unset and does not alter global configuration. This direct compatibility fix is covered by its own synthetic regression; the self-climb scores apply to the promoted completion guard patch.

QA registration: the original hill-climber and hill-climber-workbench projects point to historical isolated worktrees. Their native receipt cannot verify this canonical release. Preserve those histories and use hill-climber-current, registered to /Users/aliabassi/hill-climber, for the current source-bound task and acceptance.

## 2026-10-02 — Skeptical self-climb and adversarial recovery

Implemented two real self-climbs: twenty-four candidates across six actual improving rounds. Frozen development cases improved 13/49→36/49→47/49. Separate unseen comparisons improved 18/50→36/50 (independent reviewers authored the panel) and 8/25→21/25 (fresh host-authored withheld inputs). Stops were token_budget_exhausted and round_budget_exhausted, not perfect-score targets. Exact selected patches were integrated separately at beef01e and 1503aca. Original receipts, ledgers, patches, charts and frozen hashes are preserved in Dogfood's hill-limits-2026-10-02 review archive.

Delivered behavior: immutable-parent final-tree checks and controller-owned Git commits; safe machine-format rename/path handling; compatible whitespace; sticky SDK failure and known metering; finite exact means and chart coordinates; arbitrary boolean gate names; bounded SDK trace retention; receipt consistency checks. Subsequent direct fixes add monotonic deadlines, selection binding before private grading/application, safe stop/resume requests and exact applied-winner crash recovery. They pass 49/49 public execution cases; they were not rerun against exposed private panels.

Native verification covers 63 Python tests and 5 workbench Node tests, with zero production dependency vulnerabilities. New permanent coverage includes 26 public adversarial fixture cases and 9 durable tests. Independent review caught both a workbench error-message regression and a new stop/resume regression; both were fixed, with delayed checkpoint-driven assertions preserving the winner and exactly-once synthetic holdout completion. Cleanup extracted exact binary64 conversion/rounding and shared patch/source validation; affected checks were refreshed. Final canonical verification and acceptance are recorded by Dogfood task hill-climber-current/adversarial-limits; GitHub CI and release receipts live in the review archive.

Limits: four fresh unseen cases remained failing at the experimental selection. Later direct changes have no new private score. These checks establish bounded execution/recovery behavior, not general model quality, UI quality or an OS sandbox. Provider allocations before event delivery, indefinite uncooperative execution, hostile-writer authentication and ledger-append/state-checkpoint crashes remain outside the proven boundary. See docs/adversarial-limits.md for exact phases, authorship, costs, stops and remaining limits. Existing untracked user documents and original protected checks are preserved.
