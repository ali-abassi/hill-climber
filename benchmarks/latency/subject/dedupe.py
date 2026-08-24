"""Duplicate detection over a list of records.

`find_duplicates` returns the id of every record whose id was already seen
earlier in the list, in the order those repeats occur.
"""
from __future__ import annotations


def find_duplicates(records: list[dict]) -> list[int]:
    seen: list[dict] = []
    duplicates: list[int] = []
    for record in records:
        if any(previous["id"] == record["id"] for previous in seen):
            duplicates.append(record["id"])
        else:
            seen.append(record)
    return duplicates
