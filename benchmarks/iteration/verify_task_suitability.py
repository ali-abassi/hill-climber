"""Layer measurement, take 2.

Take 1 failed: an O(n^2) duplicate scan captured 93.6% of the gain, because a
quadratic cost always dominates linear ones at scale. Every inefficiency here
is O(total text length) so relative costs stay stable, and each is a real
pattern people write:

  A  text.lower() evaluated three separate times   -> lower once
  B  manual character loop to count vowels         -> str.count / translate
  C  " ".join(words).split() roundtrip             -> use words directly
  D  per-word string += accumulation               -> list append + join
"""
from __future__ import annotations

import random
import statistics
import time

REPEATS = 5
SIZE = 4000
VOWELS = "aeiou"


def workload(seed: int, size: int) -> list[dict]:
    rng = random.Random(seed)
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
             "iota", "kappa", "lambda", "sigma"]
    tags = [f"tag{i}" for i in range(12)]
    out = []
    for i in range(size):
        text = " ".join(rng.choice(words) for _ in range(rng.randint(20, 40)))
        out.append({"id": i, "text": text.upper(), "tag": rng.choice(tags)})
    return out


def baseline(records):
    total_vowels = 0
    total_words = 0
    initials = ""
    for record in records:
        # A: lower() three times on the same text
        words = record["text"].lower().split()
        first = record["text"].lower()[:1]
        vowel_source = record["text"].lower()
        # B: manual character loop
        count = 0
        for ch in vowel_source:
            if ch in VOWELS:
                count += 1
        total_vowels += count
        # C: join then split roundtrip
        rejoined = " ".join(words).split()
        total_words += len(rejoined)
        # D: per-word string accumulation
        acc = ""
        for w in rejoined:
            acc += w[0]
        initials += first + acc[:1]
    return total_vowels, total_words, len(initials)


def fix_a(records):
    total_vowels = total_words = 0
    initials = ""
    for record in records:
        lowered = record["text"].lower()
        words = lowered.split()
        first = lowered[:1]
        count = 0
        for ch in lowered:
            if ch in VOWELS:
                count += 1
        total_vowels += count
        rejoined = " ".join(words).split()
        total_words += len(rejoined)
        acc = ""
        for w in rejoined:
            acc += w[0]
        initials += first + acc[:1]
    return total_vowels, total_words, len(initials)


def fix_b(records):
    total_vowels = total_words = 0
    initials = ""
    for record in records:
        words = record["text"].lower().split()
        first = record["text"].lower()[:1]
        vowel_source = record["text"].lower()
        total_vowels += sum(vowel_source.count(v) for v in VOWELS)
        rejoined = " ".join(words).split()
        total_words += len(rejoined)
        acc = ""
        for w in rejoined:
            acc += w[0]
        initials += first + acc[:1]
    return total_vowels, total_words, len(initials)


def fix_c(records):
    total_vowels = total_words = 0
    initials = ""
    for record in records:
        words = record["text"].lower().split()
        first = record["text"].lower()[:1]
        vowel_source = record["text"].lower()
        count = 0
        for ch in vowel_source:
            if ch in VOWELS:
                count += 1
        total_vowels += count
        total_words += len(words)
        acc = ""
        for w in words:
            acc += w[0]
        initials += first + acc[:1]
    return total_vowels, total_words, len(initials)


def fix_d(records):
    total_vowels = total_words = 0
    parts = []
    for record in records:
        words = record["text"].lower().split()
        first = record["text"].lower()[:1]
        vowel_source = record["text"].lower()
        count = 0
        for ch in vowel_source:
            if ch in VOWELS:
                count += 1
        total_vowels += count
        rejoined = " ".join(words).split()
        total_words += len(rejoined)
        acc = [w[0] for w in rejoined]
        parts.append(first + ("".join(acc))[:1])
    return total_vowels, total_words, len("".join(parts))


def fix_all(records):
    total_vowels = total_words = 0
    parts = []
    for record in records:
        lowered = record["text"].lower()
        words = lowered.split()
        total_vowels += sum(lowered.count(v) for v in VOWELS)
        total_words += len(words)
        parts.append(lowered[:1] + (words[0][0] if words else ""))
    return total_vowels, total_words, len("".join(parts))


def timed(fn, data):
    samples = []
    for _ in range(REPEATS):
        payload = [dict(d) for d in data]
        t0 = time.perf_counter()
        fn(payload)
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples)


def main() -> None:
    data = workload(20260825, SIZE)
    expected = baseline([dict(d) for d in data])

    variants = [
        ("baseline", baseline),
        ("A lower() once", fix_a),
        ("B builtin vowel count", fix_b),
        ("C drop join/split", fix_c),
        ("D list instead of +=", fix_d),
        ("ALL fixes", fix_all),
    ]

    results = {}
    for name, fn in variants:
        got = fn([dict(d) for d in data])
        assert got == expected, f"{name} changed behaviour!\n got={got}\n want={expected}"
        results[name] = timed(fn, data)

    base = results["baseline"]
    best = results["ALL fixes"]
    total_gain = base - best

    print(f"records={SIZE} repeats={REPEATS}")
    print(f"{'variant':26s} {'median_s':>10s} {'speedup':>9s} {'share of gain':>15s}")
    print("-" * 66)
    for name, _ in variants:
        s = results[name]
        share = "" if name == "baseline" else f"{(base - s) / total_gain * 100:5.1f}%"
        print(f"{name:26s} {s:10.4f} {base/s:8.2f}x {share:>15s}")

    shares = {n: (base - results[n]) / total_gain
              for n, _ in variants if n not in ("baseline", "ALL fixes")}
    dominant = max(shares, key=shares.get)
    print()
    print(f"ceiling: {base/best:.2f}x   largest single fix: {dominant} "
          f"({shares[dominant]*100:.1f}% of gain)")
    print()
    if shares[dominant] > 0.6:
        print("UNSUITABLE: one fix dominates. Redesign.")
    else:
        print("SUITABLE: no single fix dominates; compounding required.")


if __name__ == "__main__":
    main()
