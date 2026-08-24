# Contributing

Contributions are welcome when they preserve the evidence boundary.

1. Create a branch from `trunk`.
2. Run `npm ci`.
3. Make a focused change with lifecycle coverage.
4. Run `npm run check` and `npm audit --omit=dev`.
5. Open a pull request explaining the invariant changed and the evidence added.

Do not weaken clean-tree preflight, mutable-path enforcement, detached grading,
one-time holdout semantics, finite budgets, fail-closed resume, ledger/state
integrity, or apply-after-promotion behavior merely to make a fixture pass.
