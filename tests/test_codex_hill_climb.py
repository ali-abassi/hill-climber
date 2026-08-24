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
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "codex-climb"
FAKE_SDK = ROOT / "tests" / "fixtures" / "fake_codex_sdk.mjs"
EVALUATOR = ROOT / "tests" / "fixtures" / "evaluate_climb_fixture.py"
INVALID_EVALUATOR = ROOT / "tests" / "fixtures" / "invalid_climb_evaluator.py"
FAILING_EVALUATOR = ROOT / "tests" / "fixtures" / "failing_climb_evaluator.py"
PRODUCT_PYTHON = ROOT / ".venv" / "bin" / "python"
if not PRODUCT_PYTHON.is_file():
    PRODUCT_PYTHON = Path(sys.executable)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True,
    ).stdout.strip()


class CodexHillClimbTests(unittest.TestCase):
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
            "CODEX_CLIMB_CODEX_MODULE": str(FAKE_SDK),
            "CODEX_CLIMB_FAKE_SCENARIO": scenario,
            "TOP_SECRET_FOR_CLIMB": "must-not-reach-candidate-shells",
            "NO_COLOR": "1",
        }

    def run_climb(self, root: Path, scenario: str, *, apply: bool = True) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
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
            environment["CODEX_CLIMB_FAKE_DELAY_MS"] = "10000"
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
            events = [json.loads(line) for line in (experiment / "events.jsonl").read_text().splitlines()]
            self.assertEqual(sum(event["type"] == "holdout_started" for event in events), 1)
            self.assertEqual(sum(event["type"] == "holdout_abandoned" for event in events), 1)

    def test_preflight_failures_have_distinct_machine_errors(self) -> None:
        cases = (
            ("auth", "E_AUTH", "codex login"),
            ("sdk", "E_SDK", "reinstall"),
            ("evaluator", "E_EVALUATOR_OUTPUT", "fix the evaluator"),
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
                    environment["CODEX_CLIMB_CODEX_MODULE"] = str(root / "missing-sdk.mjs")
                evaluator_path = (INVALID_EVALUATOR if case == "evaluator" else
                                  FAILING_EVALUATOR if case == "evaluator_exit" else EVALUATOR)
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


if __name__ == "__main__":
    unittest.main()
