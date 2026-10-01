# Security model

`hill-climber` narrows and records autonomous code changes; it is not an
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

## Local workbench

`hill-climber ui` listens on `127.0.0.1` and accepts only local hosts and
same-origin requests. It sets a restrictive Content Security Policy and serves
only three explicit static assets. It prepares quoted terminal commands; it
does not execute supplied evaluator text or launch real model runs. Inspection
invokes the existing controller's read-only command and checks receipt fields
against state and ledger evidence. Candidate content is rendered as text.

The deterministic demo uses fixed repository fixtures, not a model service.
The workbench has local-user access to experiment evidence. It is not a
multi-user server, does not authenticate remote users, and must not be exposed
through a network proxy, forwarding rule, or tunnel. Avoid secrets in objectives,
details and evaluator command strings; use inherited `--env KEY` in the terminal
for credentials. The UI does not store plans in browser storage.

## Reporting a vulnerability

Do not open a public issue for an unpatched vulnerability. Use GitHub's private
security advisory flow for this repository and include reproduction steps,
affected versions, impact, and any proposed fix.
