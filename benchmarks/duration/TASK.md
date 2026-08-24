# Duration parser benchmark task

Improve `parse_duration(value)` in `duration.py`.

The function must accept only strings made from one or more nonnegative ASCII
integer components using `h`, `m`, and `s`, in that order, with no whitespace
or separators. A unit may appear at most once. Missing units are allowed.

Examples:

- `"2h15m9s"` → `8109`
- `"4m3s"` → `243`
- `"0s"` → `0`

Reject malformed input by raising `ValueError`, including empty input,
non-strings, signs, decimals, unknown or uppercase units, whitespace, repeated
units, and units that appear out of order.

Do not add dependencies or edit files other than `duration.py`.
