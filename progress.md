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
