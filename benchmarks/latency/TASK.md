# Task

Reduce the wall time of `find_duplicates` in `dedupe.py`.

## Contract that must not change

`find_duplicates(records)` takes a list of dictionaries, each with an integer
`id` and a string `name`. It returns a list containing the `id` of every record
whose `id` already appeared earlier in the list, in the order those repeats
occur, with one entry per repeat.

Examples:

- `[]` returns `[]`
- `[{"id": 1}, {"id": 1}]` returns `[1]`
- `[{"id": 5}, {"id": 5}, {"id": 5}]` returns `[5, 5]`
- `[{"id": 3}, {"id": 1}, {"id": 3}]` returns `[3]`

## Boundaries

- Edit `dedupe.py` only.
- Standard library only; no new dependencies.
- Correctness is a hard gate, not part of the score. A faster function that
  returns different results scores `-1e9`.
- Do not attempt to detect or special-case the evaluator's workload. The
  promotion decision uses a different generator seed and size.
