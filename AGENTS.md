# Agent contributor guide

Read `README.md`, `SKILL.md`, `SECURITY.md`, and `docs/design.md` before editing.

The controller in `scripts/hill_climber.mjs` owns all trusted decisions.
The Python file in `bin/hill-climber` only parses CLI arguments and forwards one
JSON request. Do not move selection, evaluator interpretation, holdout access,
or source application into a model prompt.

Required checks:

```bash
npm ci
npm run check
npm audit --omit=dev
```

Every controller change needs a deterministic lifecycle assertion. Preserve
exactly-one-document JSON stdout, append-only plain stderr progress, meaningful
exit codes, and copyable resume commands. Never commit generated experiments,
candidate worktrees, authentication material, local evidence, or `node_modules`.
