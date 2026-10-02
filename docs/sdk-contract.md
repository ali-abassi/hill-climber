# Candidate completion contract

A candidate can enter grading only after one completed SDK turn supplies usable metering and the declared three-field metadata object. The controller validates that boundary locally: exact keys, nonblank strings, and maximum Unicode code-point lengths of 160 for mechanism, 1000 for hypothesis, and 2000 for summary.

Input and output token counts must be present, finite nonnegative integers with a positive total. Present known optional counts must also be finite nonnegative integers. Invalid usage stays unknown and cannot enter aggregate counters. Raw received events and the reported meter remain inspectable; valid reported usage still counts when metadata validation, provider error, timeout or interruption rejects the candidate.

The SDK continues to receive its abort signal. If a finite adapter ignores that signal and completes late, Hill Climber drains its received events and meter, then rejects the completion before generated.json, grading or promotion. Cooperative cancellation still holds the writer lock until every worker settles. This protects acceptance; it does not force termination or provide OS containment for arbitrary indefinitely hanging third-party code.

## Self-climb evidence, 2026-10-02

| Panel | Baseline | Promoted patch |
|---|---:|---:|
| Frozen development completion scenarios | 11/26 | 26/26 |
| One independent private comparison | 5/20 | 20/20 |

Two real Luna xhigh candidates both reached 26/26 and passed the existing native lifecycle, recovery and performance gates. The controller chose the smaller patch and promoted it on the private panel. The target was achieved in one round; no second round or private replay was needed. A deliberately broken controller scored 3/26 and failed the valid-candidate gate. Protected tests and external evaluators were unchanged throughout search. New permanent regressions are added after promotion.

These results establish completion-contract behavior in the defined scenarios, not broad model quality, throughput gains, strict aggregate cost limits or platform certification. The historical prompt benchmark holdout in this repository is disclosed benchmark data; this experiment uses different private cases outside the repository. One repeat is used for deterministic protocol assertions, not noisy timing optimization.

The promoted source patch is preserved exactly at integration. Local receipts, ledger, frozen-file hashes, winner.patch and report.svg live in Dogfood's review bundle for hill-self-climb-2026-10-02. Dogfood task hill-climber/self-climb-sdk-contract records release checks at the delivered revision.

## Source-informed design

Official Codex source at commit a4bfd07d51fa941d70e41cc0345b631ab5a41224 forwards outputSchema and signal while parsing streamed JSON into typed events: [thread.ts](https://github.com/openai/codex/blob/a4bfd07d51fa941d70e41cc0345b631ab5a41224/sdk/typescript/src/thread.ts). Its [abort tests](https://github.com/openai/codex/blob/a4bfd07d51fa941d70e41cc0345b631ab5a41224/sdk/typescript/tests/abort.test.ts) cover cooperative cancellation before execution and during iteration. Retain that mechanism; independently validate Hill Climber's own consuming boundary. No vendor code is copied and no dependency is added.
