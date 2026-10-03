"""Public adversarial execution regressions using isolated real CLI runs."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.fixtures.adversarial_case import run_case


ROOT = Path(__file__).resolve().parents[1]
VALID_METER = {"input_tokens": 11, "output_tokens": 7, "cached_input_tokens": 2}
TRACE_LIMIT = 2 * 1024 * 1024


class AdversarialContractTests(unittest.TestCase):
    """Guard candidate boundaries, bounded capture, and durable evidence."""

    def check_case(self, identifier: str, expected: str = "promoted", **options) -> None:
        run_case(ROOT, {"id": identifier, "expected": expected, **options})

    def test_ordinary_and_below_limit_tool_candidates_promote(self):
        self.check_case("valid-ordinary")
        self.check_case("valid-small-tools", pressure_count=12, pressure_bytes=40000)

    def test_literal_arrow_paths_follow_the_actual_mutable_boundary(self):
        self.check_case(
            "valid-arrow-filename", extra_paths=["notes -> done.txt"],
            mutable=["solution.txt", "notes -> done.txt"],
        )
        self.check_case(
            "literal-arrow-forbidden", "E_MUTABLE_BOUNDARY",
            extra_paths=["blocked -> solution.txt"],
        )

    def test_staged_rename_checks_the_original_path(self):
        self.check_case(
            "staged-rename-original-forbidden", "E_MUTABLE_BOUNDARY",
            initial_paths=["ci/x.md"], rename=["ci/x.md", "y.md"],
            mutable=["solution.txt", "*.md"],
        )

    def test_candidate_git_history_and_replacement_cannot_bypass_boundaries(self):
        self.check_case(
            "self-commit-forbidden", "E_MUTABLE_BOUNDARY", self_commit="forbidden.txt",
        )
        self.check_case(
            "gitdir-replacement-no-hooks", "E_MUTABLE_BOUNDARY", gitdir_attack=True,
        )

    def test_allowed_self_commit_keeps_the_controller_owned_parent(self):
        self.check_case(
            "self-commit-allowed", self_commit="solution.txt", immutable_parent=True,
        )

    def test_valid_crlf_and_trailing_whitespace_remain_compatible(self):
        for identifier, content in (("valid-crlf", "1\r\n"), ("valid-trailing-space", "1 \n")):
            with self.subTest(content=repr(content)):
                self.check_case(identifier, content=content)

    def test_prototype_gate_names_preserve_true_and_false_values(self):
        self.check_case("valid-prototype-gate", candidate_gates={"__proto__": True, "constructor": True})
        self.check_case("gate-false-prototype", "retained_gate", candidate_gates={"__proto__": False})

    def test_large_finite_means_and_svg_coordinates_remain_finite(self):
        self.check_case("finite-mean-large", mean_values=[1e308, 1e308])
        self.check_case(
            "finite-mean-mixed", mean_values=[1e308, 1e308, -1e308], baseline_score=-1.5e308,
        )

    def test_empty_fatal_sdk_events_are_errors_and_errors_are_sticky(self):
        events = (
            [{"type": "error", "message": ""}],
            [{"type": "turn.failed", "error": {"message": ""}}],
            [{"type": "error", "message": "fatal"}, {"type": "error", "message": ""}],
        )
        for index, after_events in enumerate(events):
            with self.subTest(events=after_events):
                self.check_case(
                    f"fatal-{index}", "E_SDK", after_events=after_events, meter_retained=True,
                )

    def test_malformed_duplicate_completion_retains_the_known_meter_once(self):
        for invalid_meter in ({"input_tokens": -2, "output_tokens": 7}, None):
            with self.subTest(invalid_meter=invalid_meter):
                self.check_case(
                    "duplicate-bad-meter", "E_SDK_EMPTY",
                    meters=[VALID_METER, invalid_meter], meter_retained=True,
                )

    def test_microtask_starved_finite_stream_obeys_candidate_deadline(self):
        self.check_case(
            "starved-deadline", "E_CANDIDATE_TIMEOUT", busy_ms=1650, meter_retained=True,
        )

    def test_single_and_many_oversized_events_keep_bounded_inspectable_traces(self):
        cases = (
            {"id": "trace-single", "pressure_count": 1, "pressure_bytes": 3 * 1024 * 1024},
            {"id": "trace-many", "pressure_count": 36, "pressure_bytes": 65536},
            {
                "id": "meter-before-trace-pressure", "pressure_count": 36, "pressure_bytes": 65536,
                "before_events": [{"type": "turn.completed", "usage": VALID_METER}],
                "meters": [], "meter_retained": True,
            },
        )
        for case in cases:
            with self.subTest(case=case["id"]):
                options = {key: value for key, value in case.items() if key != "id"}
                self.check_case(
                    case["id"], "E_SDK_LIMIT", trace_limit=TRACE_LIMIT,
                    allowed_codes=["E_SDK_LIMIT", "E_OUTPUT_LIMIT"], **options,
                )

    def test_inspect_and_resume_reject_receipt_score_promotion_and_hash_tampering(self):
        for field in ("incumbent.score", "promotion.verdict", "report.sha256"):
            with self.subTest(field=field):
                self.check_case(f"receipt-{field}", receipt_tamper=field)


if __name__ == "__main__":
    unittest.main()
