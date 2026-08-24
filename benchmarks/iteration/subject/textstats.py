"""Text statistics over a batch of records.

`summarize` returns a 3-tuple:

  total_vowels -- number of vowel characters across all record text
  total_words  -- number of whitespace-separated word tokens
  initials_len -- length of the accumulated initials string

Case is ignored throughout: all text is treated as lowercase.
"""
from __future__ import annotations

VOWELS = "aeiou"


def summarize(records: list[dict]) -> tuple[int, int, int]:
    total_vowels = 0
    total_words = 0
    initials = ""

    for record in records:
        words = record["text"].lower().split()
        first = record["text"].lower()[:1]
        vowel_source = record["text"].lower()

        count = 0
        for character in vowel_source:
            if character in VOWELS:
                count += 1
        total_vowels += count

        rejoined = " ".join(words).split()
        total_words += len(rejoined)

        accumulated = ""
        for word in rejoined:
            accumulated += word[0]

        initials += first + accumulated[:1]

    return total_vowels, total_words, len(initials)
