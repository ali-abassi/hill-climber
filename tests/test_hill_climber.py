from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "hill-climber"
FAKE_SDK = ROOT / "tests" / "fixtures" / "fake_codex_sdk.mjs"
EVALUATOR = ROOT / "tests" / "fixtures" / "evaluate_climb_fixture.py"
ENV_PROBE_EVALUATOR = ROOT / "tests" / "fixtures" / "env_probe_evaluator.py"
MULTIFILE_EVALUATOR = ROOT / "tests" / "fixtures" / "multifile_evaluator.py"
LATENCY_BENCHMARK = ROOT / "benchmarks" / "latency"
ITERATION_BENCHMARK = ROOT / "benchmarks" / "iteration"
INVALID_EVALUATOR = ROOT / "tests" / "fixtures" / "invalid_climb_evaluator.py"
INVALID_FEEDBACK_EVALUATOR = ROOT / "tests" / "fixtures" / "invalid_feedback_evaluator.py"
FAILING_EVALUATOR = ROOT / "tests" / "fixtures" / "failing_climb_evaluator.py"
BENCHMARK = ROOT / "benchmarks" / "duration"
PROTOCOL_BENCHMARK = ROOT / "benchmarks" / "protocol"
PRODUCT_PYTHON = ROOT / ".venv" / "bin" / "python"
if not PRODUCT_PYTHON.is_file():
    PRODUCT_PYTHON = Path(sys.executable)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True,
    ).stdout.strip()


class HillClimberTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "source"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        (repo / "solution.txt").write_text("0\n", encoding="utf-8")
        git(repo, "add", "solution.txt")
        git(repo, "commit", "-qm", "baseline")
        return repo

    def environment(self, root: Path, scenario: str) -> dict[str, str]:
        fake_bin = root / "bin"
        fake_bin.mkdir(exist_ok=True)
        codex = fake_bin / "codex"
        codex.write_text("#!/bin/sh\nprintf '%s\\n' 'Logged in using ChatGPT'\n", encoding="utf-8")
        codex.chmod(0o755)
        return {
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "HILL_CLIMBER_CODEX_MODULE": str(FAKE_SDK),
            "HILL_CLIMBER_FAKE_SCENARIO": scenario,
            "TOP_SECRET_FOR_CLIMB": "must-not-reach-candidate-shells",
            "NO_COLOR": "1",
        }

    def run_climb(self, root: Path, scenario: str, *, apply: bool = True,
                  rounds: int = 1) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        repo = self.make_repo(root)
        experiment = root / "experiment"
        task = (
            f"Improve the {scenario} fixture score while preserving every declared constraint; "
            "this deliberately long task must remain fully copyable in terminal output through "
            "the final marker MAXIMUM-CONTENT-TASK-END."
        )
        evaluator = shlex.join([str(PRODUCT_PYTHON), str(EVALUATOR), scenario, "development"])
        holdout = shlex.join([str(PRODUCT_PYTHON), str(EVALUATOR), scenario, "holdout"])
        command = [
            str(PRODUCT_PYTHON), str(CLI), "run",
            "--workspace", str(repo),
            "--task", task,
            "--details", "Edit solution.txt to a better integer.",
            "--eval", evaluator,
            "--holdout-eval", holdout,
            "--mutable", "solution.txt",
            "--candidates", "5",
            "--rounds", str(rounds),
            "--generation-parallel", "2",
            "--out", str(experiment),
            "--json",
        ]
        if not apply:
            command.append("--no-apply")
        result = subprocess.run(
            command, cwd=repo, env=self.environment(root, scenario),
            text=True, capture_output=True, timeout=90, check=False,
        )
        return result, repo, experiment

    def test_multi_round_demo_renders_a_literal_verified_climb(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            result, repo, experiment = self.run_climb(Path(raw), "staircase", rounds=4)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)["result"]
            self.assertEqual(receipt["status"], "promoted")
            self.assertEqual(receipt["rounds_completed"], 4)
            self.assertEqual(receipt["counts"]["candidates"], 20)
            self.assertEqual(receipt["counts"]["kept"], 4)
            self.assertEqual(receipt["baseline"]["score"], 0)
            self.assertEqual(receipt["incumbent"]["score"], 20)
            self.assertEqual((repo / "solution.txt").read_text().strip(), "20")
            report = (experiment / "report.svg").read_text(encoding="utf-8")
            self.assertIn("4 rounds. 4 verified climbs.", report)
            self.assertIn("ROUND 4", report)
            self.assertIn('class="route route-kept"', report)
            self.assertIn('class="route route-rejected"', report)

            second_round_prompt = (
                experiment / "candidates" / "r02-c01" / "prompt.txt"
            ).read_text(encoding="utf-8")
            self.assertIn("Reflect before editing", second_round_prompt)
            self.assertIn("mechanism=fixture-staircase-1-2", second_round_prompt)
            self.assertIn("actionable_feedback=Generalize the staircase improvement", second_round_prompt)
            evidence_block = second_round_prompt.lower().split(
                "visible development evidence from earlier completed work", 1
            )[1].split("reflect before editing", 1)[0]
            self.assertNotIn(":holdout:", evidence_block)

            first_result = json.loads((
                experiment / "candidates" / "r01-c01" / "result.json"
            ).read_text(encoding="utf-8"))
            self.assertEqual(first_result["evaluation"]["metrics"][0]["values"], {"value": 2})
            self.assertEqual(
                first_result["evaluation"]["feedback"],
                ["Generalize the staircase improvement without hard-coding this visible value."],
            )

            events = [
                json.loads(line)
                for line in (experiment / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            evaluated = next(event for event in events if event["type"] == "candidate_evaluated")
            self.assertEqual(evaluated["payload"]["metadata"]["mechanism"], "fixture-staircase-1-1")
            ET.fromstring(report)

    def assert_ledger_chain(self, experiment: Path) -> None:
        previous = None
        records = [json.loads(line) for line in (experiment / "events.jsonl").read_text().splitlines()]
        for expected_seq, record in enumerate(records, start=1):
            self.assertEqual(record["seq"], expected_seq)
            self.assertEqual(record["prev_hash"], previous)
            core = {key: value for key, value in record.items() if key != "hash"}
            encoded = (json.dumps(core, sort_keys=True, separators=(",", ":")) + "\n").encode()
            self.assertEqual(record["hash"], hashlib.sha256(encoded).hexdigest())
            previous = record["hash"]

    def test_easy_medium_and_hard_each_run_exactly_five_candidates(self) -> None:
        expected = {"easy": "5", "medium": "8", "hard": "12"}
        for scenario, winning_value in expected.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as raw:
                result, repo, experiment = self.run_climb(Path(raw), scenario)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                receipt = payload["result"]
                self.assertEqual(receipt["status"], "promoted")
                self.assertEqual(receipt["counts"]["candidates"], 5)
                self.assertEqual(receipt["candidates_requested"], 5)
                self.assertTrue(receipt["applied"])
                self.assertEqual((repo / "solution.txt").read_text().strip(), winning_value)
                self.assertEqual(len(list((experiment / "candidates").glob("r01-c*/turn.json"))), 5)
                self.assertEqual(len(result.stdout.strip().splitlines()), 1)
                self.assertIn("CANDIDATE 5/5", result.stderr)
                self.assertIn("MAXIMUM-CONTENT-TASK-END.", result.stderr)
                self.assertNotIn("...[truncated]", result.stderr)
                ledger_digest = hashlib.sha256((experiment / "events.jsonl").read_bytes()).hexdigest()
                self.assertEqual(receipt["evidence"]["ledger"]["sha256"], ledger_digest)
                report = experiment / "report.svg"
                self.assertTrue(report.is_file())
                report_text = report.read_text(encoding="utf-8")
                self.assertIn("Hill Climber result: promoted", report_text)
                self.assertIn("VERIFIED HILL-CLIMB TRAJECTORY", report_text)
                self.assertIn("DEV WINNER", report_text)
                self.assertIn("PROMOTED", report_text)
                ET.parse(report)
                self.assertEqual(receipt["report"]["format"], "image/svg+xml")
                self.assertEqual(receipt["report"]["sha256"], hashlib.sha256(report.read_bytes()).hexdigest())
                self.assert_ledger_chain(experiment)

    def test_hidden_holdout_rejects_development_winner_without_touching_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            result, repo, experiment = self.run_climb(Path(raw), "cheater")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)["result"]
            self.assertEqual(receipt["status"], "retained")
            self.assertEqual(receipt["promotion"]["verdict"], "reverted")
            self.assertEqual((repo / "solution.txt").read_text(), "0\n")
            self.assertFalse(receipt["applied"])
            self.assertEqual(git(repo, "status", "--porcelain"), "")
            self.assertTrue((experiment / "receipt.json").is_file())
            report_text = (experiment / "report.svg").read_text(encoding="utf-8")
            self.assertIn("Hill Climber result: retained", report_text)
            self.assertIn("REVERTED", report_text)
            self.assertIn("NO — BASELINE KEPT", report_text)

    def test_env_flag_reaches_evaluators_additively_without_leaking_parent_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            experiment = root / "experiment"
            evaluator = shlex.join([str(PRODUCT_PYTHON), str(ENV_PROBE_EVALUATOR)])
            command = [
                str(PRODUCT_PYTHON), str(CLI), "run", "--workspace", str(repo),
                "--task", "noop", "--eval", evaluator, "--holdout-eval", evaluator,
                "--env", "HC_TEST_PROBE=reached", "--mutable", "solution.txt",
                "--candidates", "1", "--out", str(experiment), "--json", "--no-apply",
            ]
            environment = self.environment(root, "easy")
            environment["HC_TEST_SECRET"] = "must-not-leak"
            result = subprocess.run(command, cwd=repo, env=environment,
                                    text=True, capture_output=True, timeout=90, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            baseline_repeat = experiment / "evaluations" / "baseline" / "development" / "repeat-1.json"
            payload = json.loads(baseline_repeat.read_text(encoding="utf-8"))
            self.assertEqual(payload["details"], "probe=reached secret=MISSING")

    def test_multi_file_candidate_is_promoted_as_one_unit_and_boundary_still_holds(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "source"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.name", "Fixture")
            git(repo, "config", "user.email", "fixture@example.test")
            (repo / "solution.txt").write_text("0\n", encoding="utf-8")
            (repo / "helper.txt").write_text("0\n", encoding="utf-8")
            (repo / "forbidden.txt").write_text("keep\n", encoding="utf-8")
            git(repo, "add", "solution.txt", "helper.txt", "forbidden.txt")
            git(repo, "commit", "-qm", "baseline")
            experiment = root / "experiment"
            evaluator = shlex.join([str(PRODUCT_PYTHON), str(MULTIFILE_EVALUATOR)])
            command = [
                str(PRODUCT_PYTHON), str(CLI), "run", "--workspace", str(repo),
                "--task", "raise solution.txt and helper.txt together",
                "--eval", evaluator, "--holdout-eval", evaluator,
                "--mutable", "solution.txt", "--mutable", "helper.txt",
                "--candidates", "2", "--rounds", "1",
                "--out", str(experiment), "--json", "--no-apply",
            ]
            result = subprocess.run(command, cwd=repo, env=self.environment(root, "multifile"),
                                    text=True, capture_output=True, timeout=90, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((experiment / "receipt.json").read_text(encoding="utf-8"))

            # The surviving candidate changed both declared files as one patch.
            self.assertEqual(receipt["incumbent"]["complexity"]["files"], 2)
            patch = (experiment / "winner.patch").read_text(encoding="utf-8")
            self.assertIn("solution.txt", patch)
            self.assertIn("helper.txt", patch)
            self.assertNotIn("forbidden.txt", patch)

            # The candidate that also wrote outside every glob was refused,
            # even though one of its two edits was legitimate.
            self.assertGreaterEqual(receipt["counts"]["invalid"], 1)
            self.assertEqual((repo / "forbidden.txt").read_text(encoding="utf-8"), "keep\n")

    def test_repository_tracked_holdout_is_refused_before_any_candidate_spend(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            # A holdout committed inside the source repository is visible to every
            # candidate, because each candidate worktree is a full clone.
            insider = repo / "holdout_evaluator.py"
            insider.write_text(
                (ENV_PROBE_EVALUATOR).read_text(encoding="utf-8"), encoding="utf-8")
            git(repo, "add", "holdout_evaluator.py")
            git(repo, "commit", "-qm", "holdout inside repo")
            experiment = root / "experiment"
            command = [
                str(PRODUCT_PYTHON), str(CLI), "run", "--workspace", str(repo),
                "--task", "noop",
                "--eval", shlex.join([str(PRODUCT_PYTHON), str(ENV_PROBE_EVALUATOR)]),
                "--holdout-eval", shlex.join([str(PRODUCT_PYTHON), str(insider)]),
                "--mutable", "solution.txt", "--candidates", "1",
                "--out", str(experiment), "--json", "--no-apply",
            ]
            result = subprocess.run(command, cwd=repo, env=self.environment(root, "easy"),
                                    text=True, capture_output=True, timeout=90, check=False)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["error"]["code"], "E_HOLDOUT_EXPOSED")
            self.assertIn("holdout_evaluator.py", payload["error"]["message"])
            # Refused before spending a single candidate turn.
            self.assertFalse((experiment / "candidates").exists())

    def test_identical_development_and_holdout_commands_are_recorded_as_dependent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            experiment = root / "experiment"
            same = shlex.join([str(PRODUCT_PYTHON), str(EVALUATOR), "easy", "development"])
            command = [
                str(PRODUCT_PYTHON), str(CLI), "run", "--workspace", str(repo),
                "--task", "noop", "--eval", same, "--holdout-eval", same,
                "--mutable", "solution.txt", "--candidates", "1",
                "--out", str(experiment), "--json", "--no-apply",
            ]
            result = subprocess.run(command, cwd=repo, env=self.environment(root, "easy"),
                                    text=True, capture_output=True, timeout=90, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((experiment / "receipt.json").read_text(encoding="utf-8"))
            # The promotion is real, but the receipt must not imply it was
            # verified against independent evidence.
            self.assertIs(receipt["promotion"]["holdout_independent"], False)
            self.assertIn("holdout command is identical", result.stderr)
            # An inert repeat-robustness gate must also be disclosed.
            self.assertIn("noise can be promoted", result.stderr)

    def test_dirty_repository_is_rejected_before_experiment_creation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            (repo / "solution.txt").write_text("dirty\n", encoding="utf-8")
            experiment = root / "experiment"
            command = [
                str(PRODUCT_PYTHON), str(CLI), "run", "--workspace", str(repo),
                "--task", "improve", "--eval", "true", "--holdout-eval", "true",
                "--mutable", "solution.txt", "--out", str(experiment), "--json",
            ]
            result = subprocess.run(command, cwd=repo, env=self.environment(root, "easy"),
                                    text=True, capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["error"]["code"], "E_DIRTY")
            self.assertIn("commit", payload["next_action"])
            self.assertFalse(experiment.exists())

    def test_resume_finishes_only_missing_work_in_an_interrupted_round(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            experiment = root / "experiment"
            evaluator = shlex.join([str(PRODUCT_PYTHON), str(EVALUATOR), "easy", "development"])
            holdout = shlex.join([str(PRODUCT_PYTHON), str(EVALUATOR), "easy", "holdout"])
            command = [
                str(PRODUCT_PYTHON), str(CLI), "run", "--workspace", str(repo),
                "--task", "Improve the easy fixture score", "--eval", evaluator,
                "--holdout-eval", holdout, "--mutable", "solution.txt", "--candidates", "5",
                "--generation-parallel", "1", "--out", str(experiment), "--json",
            ]
            environment = self.environment(root, "easy")
            environment["HILL_CLIMBER_FAKE_DELAY_MS"] = "10000"
            process = subprocess.Popen(command, cwd=repo, env=environment, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                ledger = experiment / "events.jsonl"
                if ledger.is_file() and '"type":"candidate_started"' in ledger.read_text():
                    break
                time.sleep(0.05)
            else:
                process.kill()
                self.fail("candidate generation did not start")

            stopped = subprocess.run(
                [str(PRODUCT_PYTHON), str(CLI), "stop", str(experiment), "--json"],
                cwd=repo, env=self.environment(root, "easy"), text=True,
                capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 130, stdout + stderr)

            (experiment / "stop.request").unlink()
            resumed = subprocess.run(
                [str(PRODUCT_PYTHON), str(CLI), "resume", str(experiment), "--json"],
                cwd=repo, env=self.environment(root, "easy"), text=True,
                capture_output=True, timeout=90, check=False,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            receipt = json.loads(resumed.stdout)["result"]
            self.assertEqual(receipt["counts"]["candidates"], 5)
            events = [json.loads(line) for line in (experiment / "events.jsonl").read_text().splitlines()]
            self.assertEqual(sum(event["type"] == "round_started" for event in events), 1)
            self.assertEqual(sum(event["type"] == "round_recovery_started" for event in events), 1)
            evaluated = [event["payload"]["candidate_id"] for event in events
                         if event["type"] == "candidate_evaluated"]
            self.assertEqual(len(evaluated), len(set(evaluated)))

    def test_interrupted_holdout_is_closed_and_never_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            experiment = root / "experiment"
            evaluator = shlex.join([str(PRODUCT_PYTHON), str(EVALUATOR), "slowholdout", "development"])
            holdout = shlex.join([str(PRODUCT_PYTHON), str(EVALUATOR), "slowholdout", "holdout"])
            command = [
                str(PRODUCT_PYTHON), str(CLI), "run", "--workspace", str(repo),
                "--task", "Improve a fixture score", "--eval", evaluator,
                "--holdout-eval", holdout, "--mutable", "solution.txt", "--candidates", "5",
                "--out", str(experiment), "--json",
            ]
            environment = self.environment(root, "slowholdout")
            process = subprocess.Popen(command, cwd=repo, env=environment, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                ledger = experiment / "events.jsonl"
                if ledger.is_file() and '"type":"holdout_started"' in ledger.read_text():
                    break
                time.sleep(0.05)
            else:
                process.kill()
                self.fail("holdout did not start")
            subprocess.run(
                [str(PRODUCT_PYTHON), str(CLI), "stop", str(experiment), "--json"],
                cwd=repo, env=environment, text=True, capture_output=True, timeout=30, check=True,
            )
            process.communicate(timeout=30)
            self.assertEqual(process.returncode, 130)

            resumed = subprocess.run(
                [str(PRODUCT_PYTHON), str(CLI), "resume", str(experiment), "--json"],
                cwd=repo, env=environment, text=True, capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(resumed.returncode, 1, resumed.stdout + resumed.stderr)
            receipt = json.loads(resumed.stdout)["result"]
            self.assertEqual(receipt["promotion"]["reason"], "holdout_interrupted_closed")
            self.assertEqual(receipt["status"], "retained")
            self.assertEqual((repo / "solution.txt").read_text(), "0\n")
            self.assertTrue((experiment / "report.svg").is_file())
            events = [json.loads(line) for line in (experiment / "events.jsonl").read_text().splitlines()]
            self.assertEqual(sum(event["type"] == "holdout_started" for event in events), 1)
            self.assertEqual(sum(event["type"] == "holdout_abandoned" for event in events), 1)

    def test_preflight_failures_have_distinct_machine_errors(self) -> None:
        cases = (
            ("auth", "E_AUTH", "codex login"),
            ("sdk", "E_SDK", "reinstall"),
            ("evaluator", "E_EVALUATOR_OUTPUT", "fix the evaluator"),
            ("feedback", "E_EVALUATOR_OUTPUT", "fix the evaluator"),
            ("evaluator_exit", "E_EVALUATOR", "fix the evaluator"),
        )
        for case, expected, action in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                repo = self.make_repo(root)
                experiment = root / "experiment"
                environment = self.environment(root, "easy")
                if case == "auth":
                    codex = root / "bin" / "codex"
                    codex.write_text("#!/bin/sh\nprintf '%s\\n' 'Not logged in'\nexit 1\n", encoding="utf-8")
                    codex.chmod(0o755)
                elif case == "sdk":
                    environment["HILL_CLIMBER_CODEX_MODULE"] = str(root / "missing-sdk.mjs")
                evaluator_path = (
                    INVALID_EVALUATOR if case == "evaluator" else
                    INVALID_FEEDBACK_EVALUATOR if case == "feedback" else
                    FAILING_EVALUATOR if case == "evaluator_exit" else EVALUATOR
                )
                evaluator = shlex.join([str(PRODUCT_PYTHON), str(evaluator_path), "easy", "development"])
                holdout = shlex.join([str(PRODUCT_PYTHON), str(EVALUATOR), "easy", "holdout"])
                result = subprocess.run([
                    str(PRODUCT_PYTHON), str(CLI), "run", "--workspace", str(repo),
                    "--task", "improve", "--eval", evaluator, "--holdout-eval", holdout,
                    "--mutable", "solution.txt", "--candidates", "1", "--out", str(experiment), "--json",
                ], cwd=repo, env=environment, text=True, capture_output=True, timeout=30, check=False)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["error"]["code"], expected)
                self.assertIn(action, payload["next_action"])

    def test_resume_rejects_tampered_state_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result, repo, experiment = self.run_climb(root, "easy", apply=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)["result"]
            winner_patch = experiment / "winner.patch"
            self.assertTrue(winner_patch.is_file())
            self.assertFalse(receipt["applied"])
            self.assertEqual(receipt["patch"]["sha256"], hashlib.sha256(winner_patch.read_bytes()).hexdigest())
            self.assertEqual(git(repo, "status", "--porcelain"), "")
            state_path = experiment / "state.json"
            original_state = state_path.read_text(encoding="utf-8")
            state = json.loads(original_state)
            state["incumbent"]["score"] = 999
            state_path.write_text(json.dumps(state), encoding="utf-8")
            status = subprocess.run(
                [str(PRODUCT_PYTHON), str(CLI), "status", str(experiment), "--json"],
                cwd=repo, env=self.environment(root, "easy"), text=True,
                capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(status.returncode, 3)
            self.assertEqual(json.loads(status.stdout)["error"]["code"], "E_EVIDENCE")

            state_path.write_text(original_state, encoding="utf-8")
            manifest_path = experiment / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["config"]["mutable"] = ["**"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            status = subprocess.run(
                [str(PRODUCT_PYTHON), str(CLI), "status", str(experiment), "--json"],
                cwd=repo, env=self.environment(root, "easy"), text=True,
                capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(status.returncode, 3)
            self.assertEqual(json.loads(status.stdout)["error"]["code"], "E_EVIDENCE")

    def test_disclosed_duration_benchmark_receipt_reproduces(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "duration.py").write_text(
                (BENCHMARK / "subject" / "duration.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            def evaluate(phase: str) -> dict[str, object]:
                result = subprocess.run(
                    [str(PRODUCT_PYTHON), str(BENCHMARK / "evaluate.py"), phase],
                    cwd=repo, text=True, capture_output=True, timeout=30, check=True,
                )
                return json.loads(result.stdout)

            self.assertEqual(evaluate("development")["metrics"]["passed"], 14)
            self.assertEqual(evaluate("holdout")["metrics"]["passed"], 4)
            subprocess.run(
                ["git", "apply", str(BENCHMARK / "results" / "winner.patch")],
                cwd=repo, text=True, capture_output=True, timeout=30, check=True,
            )
            self.assertEqual(evaluate("development")["score"], 1)
            self.assertEqual(evaluate("holdout")["score"], 1)

            receipt = json.loads((BENCHMARK / "results" / "receipt.json").read_text(encoding="utf-8"))
            for key, filename in (("ledger", "events.jsonl"), ("manifest", "manifest.json")):
                digest = hashlib.sha256((BENCHMARK / "results" / filename).read_bytes()).hexdigest()
                self.assertEqual(receipt["evidence"][key]["sha256"], digest)
            self.assertEqual(
                receipt["patch"]["sha256"],
                hashlib.sha256((BENCHMARK / "results" / "winner.patch").read_bytes()).hexdigest(),
            )
            self.assertEqual(
                receipt["report"]["sha256"],
                hashlib.sha256((BENCHMARK / "results" / "report.svg").read_bytes()).hexdigest(),
            )
            ET.parse(BENCHMARK / "results" / "report.svg")

    def test_disclosed_latency_benchmark_receipt_reproduces(self) -> None:
        results = LATENCY_BENCHMARK / "results"
        # A wall-time claim is machine-dependent, so this verifies the two
        # things that must hold anywhere: the promoted patch preserves
        # behaviour, and it removes the quadratic cost. Absolute seconds from
        # the disclosed run are not asserted.
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "dedupe.py").write_text(
                (LATENCY_BENCHMARK / "subject" / "dedupe.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            def evaluate(phase: str) -> dict[str, object]:
                result = subprocess.run(
                    [str(PRODUCT_PYTHON), str(LATENCY_BENCHMARK / "evaluate.py"), phase, "0.05"],
                    cwd=repo, text=True, capture_output=True, timeout=120, check=True,
                )
                return json.loads(result.stdout)

            before = {phase: evaluate(phase) for phase in ("development", "holdout")}
            for phase, payload in before.items():
                self.assertTrue(payload["gates"]["correct"], f"{phase} baseline must be correct")

            subprocess.run(
                ["git", "apply", str(results / "winner.patch")],
                cwd=repo, text=True, capture_output=True, timeout=30, check=True,
            )

            after = {phase: evaluate(phase) for phase in ("development", "holdout")}
            for phase, payload in after.items():
                # Behaviour preserved: this is the gate a "fast" wrong answer fails.
                self.assertTrue(payload["gates"]["correct"], f"{phase} patch must stay correct")
                # Quadratic cost removed. The disclosed run measured >7000x; a
                # 10x floor proves the asymptotic change without depending on
                # the speed or load of whatever machine runs this.
                speedup = abs(before[phase]["score"]) / abs(payload["score"])
                self.assertGreater(speedup, 10.0, f"{phase} speedup was only {speedup:.1f}x")

            receipt = json.loads((results / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "promoted")
            self.assertEqual(receipt["counts"],
                             {"candidates": 5, "crashed": 0, "invalid": 0, "kept": 1, "rejected": 4})
            # The disclosed run must itself have been independently verified.
            self.assertIs(receipt["promotion"]["holdout_independent"], True)
            self.assertTrue(receipt["promotion"]["holdout_used"])
            # Repeats above 1 are what make the repeat-robustness gate meaningful.
            self.assertGreaterEqual(len(receipt["baseline"]["scores"]), 3)
            self.assertGreaterEqual(len(receipt["incumbent"]["scores"]), 3)

            for key, filename in (("ledger", "events.jsonl"), ("manifest", "manifest.json")):
                digest = hashlib.sha256((results / filename).read_bytes()).hexdigest()
                self.assertEqual(receipt["evidence"][key]["sha256"], digest)
            for key, filename in (("patch", "winner.patch"), ("report", "report.svg")):
                digest = hashlib.sha256((results / filename).read_bytes()).hexdigest()
                self.assertEqual(receipt[key]["sha256"], digest)
            ET.parse(results / "report.svg")

    def test_disclosed_iteration_experiment_reproduces(self) -> None:
        # The experiment's claim is comparative: at an identical candidate
        # budget, the multi-round arm produced a faster promoted patch than the
        # one-shot arm. Wall seconds are machine-dependent, so this re-measures
        # both promoted patches here rather than trusting the recorded numbers.
        results = ITERATION_BENCHMARK / "results"
        one_shot = json.loads((results / "arm-a-one-shot" / "receipt.json").read_text(encoding="utf-8"))
        multi = json.loads((results / "arm-b-multi-round" / "receipt.json").read_text(encoding="utf-8"))

        # Equal candidate budget is what makes the comparison meaningful.
        self.assertEqual(one_shot["counts"]["candidates"], multi["counts"]["candidates"])
        # Only the multi-round arm iterated, and it took gain in more than one step.
        self.assertEqual(one_shot["rounds_completed"], 1)
        self.assertGreater(multi["rounds_completed"], 1)
        self.assertEqual(one_shot["counts"]["kept"], 1)
        self.assertGreater(multi["counts"]["kept"], 1)
        # Both promotions must have been independently verified to be comparable.
        for receipt in (one_shot, multi):
            self.assertEqual(receipt["status"], "promoted")
            self.assertIs(receipt["promotion"]["holdout_independent"], True)

        for arm in ("arm-a-one-shot", "arm-b-multi-round"):
            receipt = json.loads((results / arm / "receipt.json").read_text(encoding="utf-8"))
            for key, filename in (("ledger", "events.jsonl"), ("manifest", "manifest.json")):
                digest = hashlib.sha256((results / arm / filename).read_bytes()).hexdigest()
                self.assertEqual(receipt["evidence"][key]["sha256"], digest)
            for key, filename in (("patch", "winner.patch"), ("report", "report.svg")):
                digest = hashlib.sha256((results / arm / filename).read_bytes()).hexdigest()
                self.assertEqual(receipt[key]["sha256"], digest)
            ET.parse(results / arm / "report.svg")

        def timed_variant(patch: Path) -> tuple[float, tuple]:
            with tempfile.TemporaryDirectory() as raw:
                repo = Path(raw)
                (repo / "textstats.py").write_text(
                    (ITERATION_BENCHMARK / "subject" / "textstats.py").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                subprocess.run(["git", "init", "-q"], cwd=repo, check=True,
                               capture_output=True, timeout=30)
                subprocess.run(["git", "apply", str(patch)], cwd=repo, check=True,
                               capture_output=True, timeout=30)
                completed = subprocess.run(
                    [str(PRODUCT_PYTHON), str(ITERATION_BENCHMARK / "evaluate.py"),
                     "development", "0.08"],
                    cwd=repo, text=True, capture_output=True, timeout=180, check=True,
                )
                payload = json.loads(completed.stdout)
                return abs(float(payload["score"])), payload["gates"]

        one_shot_seconds, one_shot_gates = timed_variant(results / "arm-a-one-shot" / "winner.patch")
        multi_seconds, multi_gates = timed_variant(results / "arm-b-multi-round" / "winner.patch")

        # Neither arm bought speed by changing behaviour.
        self.assertTrue(one_shot_gates["correct"])
        self.assertTrue(multi_gates["correct"])
        # The headline comparative claim, re-measured on this machine. The
        # disclosed gap was 6.8%; 1.0 only asserts the direction, because a
        # loaded or slow machine compresses the margin.
        self.assertLess(multi_seconds, one_shot_seconds,
                        f"multi-round {multi_seconds:.5f}s was not faster than "
                        f"one-shot {one_shot_seconds:.5f}s")

    def test_disclosed_protocol_receipt_is_internally_verified(self) -> None:
        results = PROTOCOL_BENCHMARK / "results"
        receipt = json.loads((results / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "promoted")
        self.assertEqual(receipt["rounds_completed"], 4)
        self.assertEqual(receipt["counts"], {
            "candidates": 20, "crashed": 0, "invalid": 0, "kept": 4, "rejected": 16,
        })
        self.assertEqual(receipt["baseline"]["score"], 0)
        self.assertEqual(receipt["incumbent"]["score"], 20)
        for key, filename in (("ledger", "events.jsonl"), ("manifest", "manifest.json")):
            digest = hashlib.sha256((results / filename).read_bytes()).hexdigest()
            self.assertEqual(receipt["evidence"][key]["sha256"], digest)
        self.assertEqual(
            receipt["patch"]["sha256"], hashlib.sha256((results / "winner.patch").read_bytes()).hexdigest(),
        )
        report = results / "report.svg"
        self.assertEqual(receipt["report"]["sha256"], hashlib.sha256(report.read_bytes()).hexdigest())
        report_text = report.read_text(encoding="utf-8")
        self.assertIn("4 rounds. 4 verified climbs.", report_text)
        self.assertIn("ROUND 4", report_text)
        ET.parse(report)
        self.assert_ledger_chain(results)


if __name__ == "__main__":
    unittest.main()
