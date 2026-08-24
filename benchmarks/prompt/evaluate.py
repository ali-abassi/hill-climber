#!/usr/bin/env python3
"""Frozen exact-match evaluator for the disclosed prompt benchmark.

The mutable artifact is `prompt.md`. The evaluator calls a pinned cheap model
with MEDIUM reasoning and a host-enforced JSON schema, then scores exact queue
accuracy. Output formatting is therefore not prompt headroom: the runtime
forces `{"queue": <enum>}` independently of prompt text.

Development failures are bounded actionable feedback. Holdout failures never
leave this evaluator. Both datasets live outside the repository being climbed.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
REASONING_EFFORT = "medium"
API_URL = "https://inference.baseten.co/v1/chat/completions"
LABELS = (
    "auto_approve",
    "finance_review",
    "incident",
    "standard_queue",
    "security_review",
    "close_no_action",
)
MAX_WORKERS = 6
MAX_RETRIES = 5

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "support_route",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"queue": {"type": "string", "enum": list(LABELS)}},
            "required": ["queue"],
            "additionalProperties": False,
        },
    },
}


def call_model(api_key: str, prompt: str, message: str) -> tuple[str | None, str | None]:
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ],
        "temperature": 0,
        "max_tokens": 512,
        "reasoning_effort": REASONING_EFFORT,
        "response_format": RESPONSE_FORMAT,
    }
    encoded = json.dumps(body).encode("utf-8")
    for attempt in range(MAX_RETRIES):
        try:
            request = urllib.request.Request(
                API_URL,
                data=encoded,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.load(response)
            content = payload["choices"][0]["message"].get("content")
            decoded = json.loads(content or "")
            queue = decoded.get("queue")
            if queue not in LABELS:
                return None, f"schema returned invalid queue: {queue!r}"
            return queue, None
        except Exception as error:  # noqa: BLE001 - retry, then report as a gate
            if attempt == MAX_RETRIES - 1:
                return None, f"{type(error).__name__}: {error}"[:300]
            time.sleep(2 * (attempt + 1))
    return None, "unreachable"


def main() -> None:
    phase = sys.argv[1]
    if phase not in ("development", "holdout"):
        raise SystemExit(f"unknown phase: {phase}")

    api_key = os.environ.get("BASETEN_API_KEY")
    if not api_key:
        print(json.dumps({
            "score": -1e9,
            "gates": {"api_available": False, "schema_valid": False},
            "details": "BASETEN_API_KEY is required; pass it with --env BASETEN_API_KEY=...",
        }, separators=(",", ":")))
        return

    prompt = Path("prompt.md").read_text(encoding="utf-8")
    benchmark = Path(__file__).resolve().parent
    dataset_name = "dev.json" if phase == "development" else "holdout.json"
    items = json.loads((benchmark / "data" / dataset_name).read_text(encoding="utf-8"))

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        outcomes = list(pool.map(
            lambda item: call_model(api_key, prompt, item["message"]), items,
        ))
    wall = time.perf_counter() - started

    errors = [error for _, error in outcomes if error]
    predictions = [queue for queue, _ in outcomes]
    correct = sum(
        1 for prediction, item in zip(predictions, items)
        if prediction == item["label"]
    )
    accuracy = correct / len(items)

    failures = []
    for prediction, item in zip(predictions, items):
        if prediction != item["label"]:
            failures.append({
                "message": item["message"],
                "expected": item["label"],
                "predicted": prediction or "__ERROR__",
            })

    feedback = []
    if phase == "development" and failures:
        feedback.append(
            "Development misroutes (these are evidence, not holdout data): " +
            json.dumps(failures[:15], separators=(",", ":"))
        )
        feedback.append(
            "Infer general routing rules that explain these failures. Do not "
            "enumerate or memorise messages; promotion uses unseen messages."
        )

    result = {
        "score": accuracy,
        "gates": {
            "api_available": not errors,
            "schema_valid": not errors,
        },
        "details": (
            f"{phase}: {correct}/{len(items)} exact queue accuracy={accuracy:.3f}; "
            f"model={MODEL}; reasoning={REASONING_EFFORT}; wall={wall:.2f}s; "
            f"prompt_chars={len(prompt)}; errors={errors[:2]}"
        ),
        "metrics": {
            "correct": correct,
            "total": len(items),
            "accuracy": accuracy,
            "api_errors": len(errors),
            "wall_seconds": wall,
            "prompt_chars": len(prompt),
        },
        "feedback": feedback,
    }
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
