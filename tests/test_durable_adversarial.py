"""Durable recovery contracts exercised with synthetic graders and child processes.

These cases reproduce an incomplete apply checkpoint, a rehashed state projection,
and a forged lock owner. All repositories, evaluations, signals, and crashes are
confined to this test's temporary directory and disposable subprocesses.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from tests import test_hill_climber as fixtures
from tests.fixtures.adversarial_case import one_json


REHASH_STATE = r'''
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const stable = value => Array.isArray(value) ? value.map(stable) :
  (value && typeof value === 'object' ?
    Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value);
const path = process.argv[1];
const state = JSON.parse(readFileSync(path, 'utf8'));
delete state.state_hash;
state.state_hash = createHash('sha256').update(JSON.stringify(stable(state)) + '\n').digest('hex');
writeFileSync(path, JSON.stringify(stable(state)) + '\n');
'''


STOPPABLE_SDK = r'''
import {appendFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
const spec = SPEC;
export class Codex {
  startThread(options) {
    return {async runStreamed(prompt, {signal}) {
      const round = Number(prompt.match(/round (\d+)/i)[1]);
      appendFileSync(spec.turns, round + '\n');
      if (round === 2 && spec.pause_second_round) {
        writeFileSync(spec.generation_started, 'ready');
        await new Promise((resolve, reject) => {
          const timer = setTimeout(resolve, 4000);
          const abort = () => {clearTimeout(timer); reject(new Error('fixture generation aborted'));};
          if (signal.aborted) abort();
          else signal.addEventListener('abort', abort, {once: true});
        });
      }
      writeFileSync(join(options.workingDirectory, 'solution.txt'), '1\n');
      async function* events() {
        yield {type: 'thread.started', thread_id: 'stoppable-round-' + round};
        yield {type: 'item.completed', item: {type: 'agent_message', text: JSON.stringify({
          mechanism: 'stoppable-fixture', hypothesis: 'Improve a synthetic integer.',
          summary: 'A bounded synthetic turn.'
        })}};
        yield {type: 'turn.completed', usage: {input_tokens: 1, output_tokens: 1}};
      }
      return {events: events()};
    }};
  }
}
'''


class DurableAdversarialTests(unittest.TestCase):
    """Recovery must use committed grading and patch evidence, not editable claims."""

    def prepare(self, root: Path, *, block_apply: bool = False):
        repo = fixtures.HillClimberTests.make_repo(self, root)
        (repo / "protected.txt").write_text("preserve\n", encoding="utf-8")
        fixtures.git(repo, "add", "protected.txt")
        fixtures.git(repo, "commit", "-qm", "protected fixture")
        experiment = root / "experiment"
        calls = root / "synthetic-holdout-calls.txt"
        blocker = repo / "apply-blocker.txt"
        evaluator = root / "synthetic-evaluate.py"
        evaluator.write_text(
            "import json, os\nfrom pathlib import Path\n"
            "candidate = os.environ['HILL_CLIMBER_CANDIDATE']\n"
            "if os.environ['HILL_CLIMBER_PHASE'] == 'holdout':\n"
            f"    with Path({str(calls)!r}).open('a') as stream: stream.write(candidate + '\\n')\n"
            f"    if {block_apply!r} and candidate == 'holdout-candidate':\n"
            f"        Path({str(blocker)!r}).write_text('block apply after grading')\n"
            "print(json.dumps({'score': int(Path('solution.txt').read_text()), 'gates': {'valid': True}}))\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith(("HILL_CLIMBER_", "PAL_")):
                environment.pop(key)
        fake_environment = fixtures.HillClimberTests.environment(self, root, "easy")
        for key in ("PATH", "HILL_CLIMBER_CODEX_MODULE", "HILL_CLIMBER_FAKE_SCENARIO", "NO_COLOR"):
            environment[key] = fake_environment[key]
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        evaluator_argv = shlex.join([str(fixtures.PRODUCT_PYTHON), str(evaluator)])
        command = [
            str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI), "run", "--json",
            "--workspace", str(repo), "--task", "Improve a synthetic integer",
            "--eval", evaluator_argv, "--holdout-eval", evaluator_argv,
            "--mutable", "solution.txt", "--candidates", "2", "--rounds", "1",
            "--generation-parallel", "1", "--candidate-timeout", "3",
            "--eval-timeout", "3", "--max-wall-seconds", "20", "--out", str(experiment),
        ]
        return repo, experiment, calls, blocker, environment, command

    def invoke(self, command, repo, environment):
        return subprocess.run(
            command, cwd=repo, env=environment, text=True, capture_output=True,
            timeout=30, check=False,
        )

    def action(self, action, experiment, repo, environment):
        return self.invoke(
            [str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI), action, str(experiment), "--json"],
            repo, environment,
        )

    def events(self, experiment):
        return [
            json.loads(line)
            for line in (experiment / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]

    def completed_before_apply(self, root):
        setup = self.prepare(root, block_apply=True)
        repo, experiment, calls, blocker, environment, command = setup
        initial = self.invoke(command, repo, environment)
        self.assertEqual(initial.returncode, 2, initial.stdout + initial.stderr)
        self.assertEqual(one_json(initial)["error"]["code"], "E_DIRTY")
        self.assertFalse((experiment / "receipt.json").exists())
        self.assertEqual(sum(event["type"] == "holdout_completed" for event in self.events(experiment)), 1)
        self.assertEqual(calls.read_text().splitlines(), ["holdout-baseline", "holdout-candidate"])
        blocker.unlink()
        self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")
        return setup

    def test_missing_receipt_with_unchanged_promoted_state_recovers_without_regrading(self):
        """Control: missing output is recoverable when the durable winner is unchanged."""
        with tempfile.TemporaryDirectory(prefix="hill-durable-control-") as raw:
            repo, experiment, calls, _, environment, _ = self.completed_before_apply(Path(raw))
            before_calls = calls.read_bytes()
            resumed = self.action("resume", experiment, repo, environment)
            document = one_json(resumed)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            self.assertEqual(document["result"]["status"], "promoted")
            self.assertTrue(document["result"]["applied"])
            self.assertEqual((repo / "solution.txt").read_text(), "5\n")
            self.assertEqual(calls.read_bytes(), before_calls)
            self.assertFalse((experiment / "run.lock").exists())

    def test_rehashed_incumbent_substitution_cannot_apply_a_holdout_ungraded_candidate(self):
        """A self-consistent state hash cannot substitute a rejected development candidate."""
        with tempfile.TemporaryDirectory(prefix="hill-durable-state-") as raw:
            repo, experiment, calls, _, environment, _ = self.completed_before_apply(Path(raw))
            state_path = experiment / "state.json"
            state = json.loads(state_path.read_text())
            rejected = json.loads((experiment / "candidates/r01-c01/result.json").read_text())
            self.assertEqual(state["incumbent"]["id"], "r01-c02")
            self.assertTrue(any(
                event["type"] == "candidate_rejected" and event["payload"]["candidate_id"] == "r01-c01"
                for event in self.events(experiment)
            ))
            started = next(event for event in self.events(experiment) if event["type"] == "holdout_started")
            self.assertNotEqual(started["payload"]["candidate"], rejected["commit"])
            state["incumbent"] = {
                "id": "r01-c01", "commit": rejected["commit"],
                **{key: rejected["evaluation"][key] for key in ("score", "low", "high", "scores", "gates")},
                "complexity": rejected["complexity"],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            subprocess.run(["node", "--input-type=module", "-e", REHASH_STATE, str(state_path)], check=True)
            before_ledger = (experiment / "events.jsonl").read_bytes()
            before_calls = calls.read_bytes()
            resumed = self.action("resume", experiment, repo, environment)
            document = one_json(resumed)
            self.assertEqual((repo / "solution.txt").read_text(), "0\n", "Ungraded substitute was applied")
            self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")
            self.assertEqual(resumed.returncode, 3, resumed.stdout + resumed.stderr)
            self.assertEqual(document.get("error", {}).get("code"), "E_EVIDENCE")
            self.assertEqual((experiment / "events.jsonl").read_bytes(), before_ledger)
            self.assertEqual(calls.read_bytes(), before_calls)
            self.assertFalse((experiment / "receipt.json").exists())
            self.assertFalse((experiment / "run.lock").exists())

    def test_rehashed_rejected_selection_fails_before_starting_synthetic_holdout(self):
        """A valid chained search checkpoint must bind the winner before any holdout starts."""
        with tempfile.TemporaryDirectory(prefix="hill-durable-pre-holdout-") as raw:
            repo, experiment, calls, _, environment, _ = self.completed_before_apply(Path(raw))
            ledger = experiment / "events.jsonl"
            lines = ledger.read_bytes().splitlines(keepends=True)
            records = [json.loads(line) for line in lines]
            holdout_index = next(
                index for index, event in enumerate(records) if event["type"] == "holdout_started"
            )
            checkpoint = records[holdout_index - 1]
            self.assertEqual(checkpoint["type"], "search_stopped")
            # Preserve each retained event's original bytes and existing hash
            # chain. Only restore the pre-holdout projection and substitute its
            # incumbent; no evaluator output or external panel is modified.
            ledger.write_bytes(b"".join(lines[:holdout_index]))
            state_path = experiment / "state.json"
            state = json.loads(state_path.read_text())
            rejected = json.loads((experiment / "candidates/r01-c01/result.json").read_text())
            state["ledger_seq"] = checkpoint["seq"]
            state["ledger_hash"] = checkpoint["hash"]
            state["status"] = "searching"
            state["incumbent"] = {
                "id": "r01-c01", "commit": rejected["commit"],
                **{key: rejected["evaluation"][key] for key in ("score", "low", "high", "scores", "gates")},
                "complexity": rejected["complexity"],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            subprocess.run(["node", "--input-type=module", "-e", REHASH_STATE, str(state_path)], check=True)
            before_calls = calls.read_bytes()
            self.assertFalse(any(event["type"] == "holdout_started" for event in self.events(experiment)))
            resumed = self.action("resume", experiment, repo, environment)
            document = one_json(resumed)
            self.assertEqual(resumed.returncode, 3, resumed.stdout + resumed.stderr)
            self.assertEqual(document.get("error", {}).get("code"), "E_EVIDENCE")
            self.assertEqual(calls.read_bytes(), before_calls, "Tampered selection consumed synthetic holdout")
            self.assertFalse(any(event["type"] == "holdout_started" for event in self.events(experiment)))
            self.assertEqual((repo / "solution.txt").read_text(), "0\n")
            self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")
            self.assertFalse((experiment / "receipt.json").exists())
            self.assertFalse((experiment / "run.lock").exists())

    def test_stop_request_does_not_signal_an_unrelated_live_lock_pid(self):
        """Use a disposable signal observer, never a real session PID."""
        with tempfile.TemporaryDirectory(prefix="hill-durable-stop-") as raw:
            root = Path(raw)
            repo, experiment, _, _, environment, command = self.prepare(root)
            initial = self.invoke([*command, "--no-apply"], repo, environment)
            self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
            one_json(initial)
            observed_signal = root / "unrelated-child-signaled"
            child_code = (
                "import signal, sys\nfrom pathlib import Path\n"
                f"signal.signal(signal.SIGINT, lambda *_: Path({str(observed_signal)!r}).write_text('SIGINT'))\n"
                "print('ready', flush=True)\n"
                "for request in sys.stdin:\n"
                "    print('checked', flush=True)\n"
            )
            child = subprocess.Popen(
                [str(fixtures.PRODUCT_PYTHON), "-u", "-c", child_code],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                lock = experiment / "run.lock"
                owner = json.dumps({"pid": child.pid, "started_at": "unrelated-fixture-process"})
                lock.write_text(owner, encoding="utf-8")
                stopped = self.action("stop", experiment, repo, environment)
                one_json(stopped)
                self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
                self.assertTrue((experiment / "stop.request").exists())
                self.assertEqual(lock.read_text(), owner, "Stop replaced another process's lock")
                child.stdin.write("check\n")
                child.stdin.flush()
                self.assertEqual(child.stdout.readline().strip(), "checked")
                self.assertIsNone(child.poll(), "Stop terminated an unrelated live process")
                self.assertFalse(observed_signal.exists(), "Stop sent SIGINT to an unrelated PID")
            finally:
                if child.poll() is None:
                    child.terminate()
                child.communicate(timeout=5)

    def crash_after_apply(self, root):
        """Kill only the test controller immediately after its successful source apply."""
        setup = self.prepare(root)
        repo, experiment, calls, _, environment, command = setup
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        crash_bin = root / "crash-bin"
        crash_bin.mkdir()
        fired = root / "apply-crash-fired"
        wrapper = crash_bin / "git"
        wrapper.write_text(
            f"#!{fixtures.PRODUCT_PYTHON}\n"
            "import os, signal, subprocess, sys\nfrom pathlib import Path\n"
            "arguments = sys.argv[1:]\n"
            f"result = subprocess.run([{real_git!r}, *arguments], check=False)\n"
            "if result.returncode == 0 and arguments and arguments[0] == 'apply' "
            "and '--check' not in arguments and '--cached' not in arguments "
            f"and Path.cwd() == Path({str(repo)!r}).resolve() and not Path({str(fired)!r}).exists():\n"
            f"    Path({str(fired)!r}).write_text(str(os.getppid()))\n"
            "    os.kill(os.getppid(), signal.SIGKILL)\n"
            "raise SystemExit(result.returncode)\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        crashing_environment = {**environment, "PATH": str(crash_bin) + os.pathsep + environment["PATH"]}
        initial = self.invoke(command, repo, crashing_environment)
        self.assertNotEqual(initial.returncode, 0, "Crash injector did not interrupt the controller")
        self.assertTrue(fired.exists(), initial.stdout + initial.stderr)
        state = json.loads((experiment / "state.json").read_text())
        self.assertFalse(state["applied"], "Crash happened after applied checkpoint")
        self.assertEqual(state["status"], "promoted")
        self.assertEqual((repo / "solution.txt").read_text(), "5\n")
        self.assertEqual(fixtures.git(repo, "diff", "--cached"), "")
        events = self.events(experiment)
        self.assertEqual(sum(event["type"] == "winner_patch_prepared" for event in events), 1)
        self.assertFalse(any(event["type"] == "winner_applied" for event in events))
        self.assertFalse((experiment / "receipt.json").exists())
        self.assertEqual(calls.read_text().splitlines(), ["holdout-baseline", "holdout-candidate"])
        return setup

    def test_resume_recovers_exact_applied_patch_without_rerunning_holdout(self):
        """The apply-to-ledger crash window must recover exactly once."""
        with tempfile.TemporaryDirectory(prefix="hill-durable-apply-") as raw:
            repo, experiment, calls, _, environment, _ = self.crash_after_apply(Path(raw))
            patch = (experiment / "winner.patch").read_bytes()
            before_calls = calls.read_bytes()
            head = fixtures.git(repo, "rev-parse", "HEAD")
            resumed = self.action("resume", experiment, repo, environment)
            document = one_json(resumed)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            self.assertEqual(document["result"]["status"], "promoted")
            self.assertTrue(document["result"]["applied"])
            self.assertEqual((repo / "solution.txt").read_text(), "5\n")
            self.assertEqual((repo / "protected.txt").read_text(), "preserve\n")
            self.assertEqual(fixtures.git(repo, "rev-parse", "HEAD"), head)
            self.assertEqual(fixtures.git(repo, "diff", "--cached"), "")
            self.assertEqual((experiment / "winner.patch").read_bytes(), patch)
            self.assertEqual(calls.read_bytes(), before_calls)
            repeated = self.action("resume", experiment, repo, environment)
            self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
            one_json(repeated)
            self.assertEqual(sum(event["type"] == "winner_applied" for event in self.events(experiment)), 1)
            self.assertEqual(calls.read_bytes(), before_calls)
            self.assertFalse((experiment / "run.lock").exists())

    def test_apply_crash_recovery_rejects_unrelated_source_edits(self):
        """An applied winner plus another source edit is drift, never partial recovery."""
        with tempfile.TemporaryDirectory(prefix="hill-durable-drift-") as raw:
            repo, experiment, calls, _, environment, _ = self.crash_after_apply(Path(raw))
            (repo / "protected.txt").write_text("unrelated edit\n", encoding="utf-8")
            before_calls = calls.read_bytes()
            resumed = self.action("resume", experiment, repo, environment)
            document = one_json(resumed)
            self.assertEqual(resumed.returncode, 3, resumed.stdout + resumed.stderr)
            self.assertEqual(document.get("error", {}).get("code"), "E_DRIFT")
            self.assertEqual((repo / "solution.txt").read_text(), "5\n")
            self.assertEqual((repo / "protected.txt").read_text(), "unrelated edit\n")
            self.assertEqual(calls.read_bytes(), before_calls)
            self.assertFalse(any(event["type"] == "winner_applied" for event in self.events(experiment)))
            self.assertFalse((experiment / "run.lock").exists())

    def stoppable_fixture(self, root, *, rounds=1, development_delay=0.0, pause_second_round=False):
        """Use explicit start markers and delays longer than the stop polling interval."""
        repo, experiment, _, _, environment, _ = self.prepare(root)
        turns = root / "sdk-turns.txt"
        development_started = root / "development-started"
        development_completed = root / "development-completed.txt"
        generation_started = root / "generation-started"
        holdout_started = root / "holdout-started.txt"
        holdout_completed = root / "holdout-completed.txt"
        sdk = root / "stoppable-sdk.mjs"
        sdk.write_text(STOPPABLE_SDK.replace("SPEC", json.dumps({
            "turns": str(turns), "generation_started": str(generation_started),
            "pause_second_round": pause_second_round,
        })), encoding="utf-8")
        environment["HILL_CLIMBER_CODEX_MODULE"] = str(sdk)
        development = root / "delayed-development.py"
        development.write_text(
            "import json, time\nfrom pathlib import Path\n"
            "value = int(Path('solution.txt').read_text())\n"
            "if value:\n"
            f"    Path({str(development_started)!r}).write_text('started')\n"
            f"    time.sleep({development_delay!r})\n"
            f"    with Path({str(development_completed)!r}).open('a') as stream: stream.write('completed\\n')\n"
            "print(json.dumps({'score': value, 'gates': {'valid': True}}))\n",
            encoding="utf-8",
        )
        synthetic_holdout = root / "delayed-synthetic-holdout.py"
        synthetic_holdout.write_text(
            "import json, os, time\nfrom pathlib import Path\n"
            "candidate = os.environ['HILL_CLIMBER_CANDIDATE']\n"
            f"with Path({str(holdout_started)!r}).open('a') as stream: stream.write(candidate + '\\n')\n"
            "time.sleep(1.5)\n"
            "value = int(Path('solution.txt').read_text())\n"
            f"with Path({str(holdout_completed)!r}).open('a') as stream: stream.write(candidate + '\\n')\n"
            "print(json.dumps({'score': value, 'gates': {'valid': True}}))\n",
            encoding="utf-8",
        )
        command = [
            str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI), "run", "--json",
            "--workspace", str(repo), "--task", "Improve a synthetic integer",
            "--eval", shlex.join([str(fixtures.PRODUCT_PYTHON), str(development)]),
            "--holdout-eval", shlex.join([str(fixtures.PRODUCT_PYTHON), str(synthetic_holdout)]),
            "--mutable", "solution.txt", "--candidates", "1", "--rounds", str(rounds),
            "--plateau-rounds", "5", "--generation-parallel", "1",
            "--candidate-timeout", "6", "--eval-timeout", "5", "--max-wall-seconds", "30",
            "--out", str(experiment), "--no-apply",
        ]
        markers = {
            "turns": turns, "development_started": development_started,
            "development_completed": development_completed, "generation_started": generation_started,
            "holdout_started": holdout_started, "holdout_completed": holdout_completed,
        }
        return repo, experiment, environment, command, markers

    def stop_at_marker(self, repo, experiment, environment, command, marker):
        """Wait for an observable fixture checkpoint before requesting an interruption."""
        process = subprocess.Popen(
            command, cwd=repo, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 15
            while not marker.exists():
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    self.fail(f"Controller exited before stop checkpoint: {stdout}\n{stderr}")
                if time.monotonic() >= deadline:
                    self.fail("Synthetic stop checkpoint timed out")
                time.sleep(0.01)
            stopped = self.action("stop", experiment, repo, environment)
            one_json(stopped)
            self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
            stdout, stderr = process.communicate(timeout=15)
            interrupted = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            self.assertEqual(process.returncode, 130, stdout + stderr)
            self.assertEqual(one_json(interrupted).get("error", {}).get("code"), "E_INTERRUPTED")
            self.assertTrue((experiment / "stop.request").exists())
            self.assertFalse((experiment / "run.lock").exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def assert_stopped_winner(self, repo, experiment, markers, result, expected_turns):
        document = one_json(result)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(document["result"]["status"], "promoted")
        self.assertEqual(document["result"]["incumbent"]["id"], "r01-c01")
        self.assertFalse(document["result"]["applied"])
        self.assertEqual(markers["turns"].read_text().splitlines(), expected_turns)
        expected_holdout = ["holdout-baseline", "holdout-candidate"]
        self.assertEqual(markers["holdout_started"].read_text().splitlines(), expected_holdout)
        self.assertEqual(markers["holdout_completed"].read_text().splitlines(), expected_holdout)
        event_types = [event["type"] for event in self.events(experiment)]
        self.assertEqual(event_types.count("holdout_started"), 1)
        self.assertEqual(event_types.count("holdout_completed"), 1)
        self.assertNotIn("holdout_abandoned", event_types)
        self.assertEqual((repo / "solution.txt").read_text(), "0\n")
        self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")
        self.assertFalse((experiment / "run.lock").exists())

    def test_delayed_synthetic_evaluation_and_holdout_promote_without_stop(self):
        """Control: both deliberately slow graders are valid without interruption."""
        with tempfile.TemporaryDirectory(prefix="hill-stale-stop-control-") as raw:
            repo, experiment, environment, command, markers = self.stoppable_fixture(
                Path(raw), development_delay=1.5,
            )
            result = self.invoke(command, repo, environment)
            self.assert_stopped_winner(repo, experiment, markers, result, ["1"])
            self.assertEqual(markers["development_completed"].read_text().splitlines(), ["completed"])

    def test_resume_drains_generated_evaluation_despite_existing_stop_request(self):
        """A prior request stops new turns while a 1.5s pending evaluation may finish."""
        with tempfile.TemporaryDirectory(prefix="hill-stale-stop-evaluation-") as raw:
            repo, experiment, environment, command, markers = self.stoppable_fixture(
                Path(raw), development_delay=1.5,
            )
            self.stop_at_marker(
                repo, experiment, environment, command, markers["development_started"],
            )
            before = [event["type"] for event in self.events(experiment)]
            self.assertEqual(before.count("candidate_generated"), 1)
            self.assertNotIn("candidate_evaluated", before)
            self.assertFalse(markers["holdout_started"].exists())
            self.assertEqual(markers["turns"].read_text().splitlines(), ["1"])
            resumed = self.action("resume", experiment, repo, environment)
            self.assert_stopped_winner(repo, experiment, markers, resumed, ["1"])
            self.assertEqual(markers["development_completed"].read_text().splitlines(), ["completed"])
            events = [event["type"] for event in self.events(experiment)]
            self.assertEqual(events.count("candidate_started"), 1)
            self.assertEqual(events.count("candidate_evaluated"), 1)
            self.assertEqual(events.count("run_interrupted"), 1)

    def test_resume_preserves_kept_winner_and_completes_delayed_holdout_once(self):
        """Stopping round two must not poison the one-time holdout of round one's winner."""
        with tempfile.TemporaryDirectory(prefix="hill-stale-stop-holdout-") as raw:
            repo, experiment, environment, command, markers = self.stoppable_fixture(
                Path(raw), rounds=2, pause_second_round=True,
            )
            self.stop_at_marker(
                repo, experiment, environment, command, markers["generation_started"],
            )
            kept = [event for event in self.events(experiment) if event["type"] == "candidate_kept"]
            self.assertEqual([event["payload"]["candidate_id"] for event in kept], ["r01-c01"])
            self.assertEqual(markers["turns"].read_text().splitlines(), ["1", "2"])
            self.assertFalse(markers["holdout_started"].exists())
            resumed = self.action("resume", experiment, repo, environment)
            self.assert_stopped_winner(repo, experiment, markers, resumed, ["1", "2"])
            completed = markers["holdout_completed"].read_bytes()
            repeated = self.action("resume", experiment, repo, environment)
            self.assert_stopped_winner(repo, experiment, markers, repeated, ["1", "2"])
            self.assertEqual(markers["holdout_completed"].read_bytes(), completed)
            events = [event["type"] for event in self.events(experiment)]
            self.assertEqual(events.count("candidate_started"), 2)
            self.assertEqual(events.count("candidate_evaluated"), 1)
            self.assertEqual(events.count("run_interrupted"), 1)


if __name__ == "__main__":
    unittest.main()
