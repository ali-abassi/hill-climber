# Codex Hill Climb

Run bounded five-candidate Codex SDK hill climbs against a Git repository.
Codex proposes changes; a local deterministic controller owns isolation,
evaluation, selection, recovery, holdout promotion, and source application.

It uses the ChatGPT subscription already authenticated by `codex login`. No
OpenAI API key is required.

## Why this exists

Prompt-only optimization loops ask an agent to edit, test, and decide whether
its own work is better. `codex-climb` separates those responsibilities:

1. Measure the untouched baseline.
2. Generate five candidates from the same immutable commit in isolated Git
   worktrees.
3. Grade every candidate in a separate detached worktree.
4. Keep at most one strict development-set improvement.
5. Run a private holdout once after search ends.
6. Apply the winner only when the holdout also passes and does not regress.

Rejected or invalid candidates never touch the source checkout. Interrupted
runs resume from durable, hash-chained evidence instead of starting over.

## Requirements

- macOS or a Linux-like local environment
- Git
- Node.js 18 or newer
- Python 3.9 or newer
- [Codex CLI](https://developers.openai.com/codex/cli/) authenticated with
  `codex login`

## Install

```bash
git clone https://github.com/ali-abassi/codex-hill-climb.git
cd codex-hill-climb
./install.sh
codex-climb --help
```

The installer downloads the two pinned Node dependencies and links
`codex-climb` into `~/.local/bin`. It does not require `sudo`.

To run directly from a checkout instead:

```bash
npm ci
./bin/codex-climb --help
```

## Quick start

Start with a clean Git repository and deterministic development and holdout
evaluators:

```bash
cd /path/to/your-project
git status --short
codex login status

codex-climb run \
  --workspace . \
  --task "Make parse_duration strict and support compound durations" \
  --details-file task.md \
  --eval "python3 /absolute/evals/dev_evaluator.py" \
  --holdout-eval "python3 /absolute/private/holdout_evaluator.py" \
  --mutable "src/**/*.py" \
  --candidates 5 \
  --rounds 1 \
  --out /tmp/duration-climb \
  --no-apply
```

`--no-apply` is a good first-run default. The promoted patch and evidence stay
in the experiment directory for inspection. Omit it when you want a
holdout-promoted patch applied automatically to the still-clean source tree.

## Evaluator contract

Both evaluators run with the candidate checkout as their working directory.
They must print exactly one JSON object:

```json
{
  "score": 0.85,
  "gates": {
    "tests": true,
    "lint": true
  },
  "details": "17 of 20 behavioral cases passed"
}
```

Scores are maximized. Every gate must be a boolean, and every gate must pass.
Use a granular score when possible: the fraction of behavioral cases passed is
more useful than a single pass/fail bit.

Keep holdout code and data outside the candidate repository. Do not mention
holdout cases in the task, details, setup command, development diagnostics, or
mutable paths. A starter binary command evaluator is included at
[`examples/binary_command_evaluator.py`](examples/binary_command_evaluator.py).

The evaluator receives these environment variables:

- `CODEX_CLIMB_PHASE`: `development`, `holdout`, or `setup`
- `CODEX_CLIMB_SEED`: paired-evaluation seed
- `CODEX_CLIMB_CANDIDATE`: candidate identifier when applicable

## Operating a run

```bash
codex-climb status /tmp/duration-climb --json
codex-climb inspect /tmp/duration-climb --json
codex-climb inspect /tmp/duration-climb --candidate r01-c03 --json
codex-climb stop /tmp/duration-climb --json
codex-climb resume /tmp/duration-climb
```

Ctrl-C checkpoints the experiment and prints the exact resume command.
Completed candidates are not regenerated or reevaluated on resume. If an
interruption occurs after private holdout evaluation begins, that holdout is
closed and never replayed; the baseline is retained.

Each experiment contains:

- a frozen manifest and self-hashed state projection;
- a fsynced, hash-chained event ledger;
- candidate prompts, Codex SDK traces, patches, and failures;
- detached development and holdout evaluation records;
- a terminal receipt describing promotion, application, usage, and stop reason.

## Useful controls

```text
--rounds 3                 up to three rounds, five new candidates each
--generation-parallel 3    generate three candidates concurrently
--repeats 3                repeat paired development grading
--holdout-repeats 3        repeat paired private grading
--setup "npm ci"           prepare each isolated worktree
--min-gain 0.05            require a meaningful score increase
--target-score 0.95        stop after reaching the target
--plateau-rounds 2         stop after two non-improving rounds
--max-wall-seconds 3600    total wall-clock budget
--max-tokens 500000        recorded Codex token stopping budget
--max-failures 5           candidate failure circuit breaker
--no-apply                 preserve the winner without touching source
```

Five candidates, one round, two concurrent generations, Terra with medium
reasoning, and finite time/token/failure budgets are the defaults.

## Safety model

- The source repository must begin clean.
- Authored changes outside `--mutable` invalidate a candidate.
- Candidate Codex threads receive workspace-write sandbox settings, no
  approvals, no web search, and network disabled through the SDK options.
- Evaluators execute as ordinary local processes with your user authority.
- This project is not an OS-level sandbox. Do not run untrusted evaluator or
  setup commands; use an external sandbox when stronger effect isolation is
  required.
- The controller never pushes, merges, deploys, or resets the user's branch.

See [SECURITY.md](SECURITY.md) and the [design notes](docs/design.md) for the
full boundary and research lineage.

## Tests

```bash
npm ci
npm test
```

The deterministic suite covers easy, medium, and hard five-candidate runs,
hidden-holdout rejection, interrupted-round recovery, interrupted-holdout
closure, distinct preflight failures, and evidence tamper rejection.

## Agent use

[`SKILL.md`](SKILL.md) is a ready-to-load operating skill for coding agents. It
defines when to use the tool, how to freeze evaluators, how to supervise and
resume runs, and what evidence is required before accepting a result.

## License

[MIT](LICENSE). This is a clean-room implementation informed by public design
patterns; no source was copied from AutoAgent or autoresearch.
