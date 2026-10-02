# Progress

## 2026-10-02 — Self-climb completion refinement

Implemented the holdout-promoted controller guard patch. Completion metadata now follows the declared exact schema; invalid metering cannot corrupt totals; valid reported usage and received evidence survive rejection; cancelled/expired finite completions cannot enter grading or promotion. Permanent synthetic regressions cover valid Unicode boundaries, schema failures, meter failures, expired responses, user cancellation, provider errors and evidence inspection.

Measured by the real self-climb: two candidates, one round, 11/26 to 26/26 development scenarios, and 5/20 to 20/20 independent private scenarios. Existing native lifecycle/recovery/performance gates pass throughout the experiment. Release validation uses npm ci, npm run check and npm audit --omit=dev; source-bound receipts and acceptance are recorded in Dogfood task self-climb-sdk-contract. The experiment chart and immutable artifacts remain in Dogfood's local review bundle.

This measures the completion contract, with finite synthetic SDK responses. It does not establish general model quality, force termination, OS containment, throughput or production readiness. Existing untracked user documents are preserved; account/global configuration and real sessions remain unchanged.
