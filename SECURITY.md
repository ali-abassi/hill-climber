# Security model

`codex-climb` narrows and records autonomous code changes; it is not an
OS-level sandbox.

## Trust boundary

- Candidate Codex SDK threads receive workspace-write sandbox settings, no
  approvals, no web search, and network disabled in SDK options.
- Candidate-authored Git diffs are limited to declared `--mutable` globs.
- Evaluator and setup commands are trusted local programs executed with the
  invoking user's authority. Their files, subprocesses, network activity, and
  external effects are not sandboxed by this project.
- The controller passes candidate threads an environment allowlist for cached
  subscription authentication rather than the caller's arbitrary environment.
- The private holdout is withheld from candidate prompts and is invoked once
  after search. Keep its code and data outside the repository to preserve that
  boundary.

Run unknown repositories, dependency installers, or evaluators inside a
separate container, VM, or other sandbox appropriate to their risk.

## Reporting a vulnerability

Do not open a public issue for an unpatched vulnerability. Use GitHub's private
security advisory flow for this repository and include reproduction steps,
affected versions, impact, and any proposed fix.
