import sys

print("first diagnostic line", file=sys.stderr)
print("second diagnostic line with a deliberately long explanation", file=sys.stderr)
raise SystemExit(7)
