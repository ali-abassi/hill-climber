from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from tests import test_hill_climber as fixtures


class ControllerRecoveryTests(unittest.TestCase):
    # Reuse fixture setup without inheriting or rerunning its test methods.
    make_repo = fixtures.HillClimberTests.make_repo
    environment = fixtures.HillClimberTests.environment

    def command(self, repo: Path, experiment: Path, evaluator: Path,
                *, candidates: int = 2) -> list[str]:
        argv = shlex.join([str(fixtures.PRODUCT_PYTHON), str(evaluator)])
        return [str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI), "run",
                "--workspace", str(repo), "--task", "Improve the integer score",
                "--eval", argv, "--holdout-eval", argv,
                "--mutable", "solution.txt", "--candidates", str(candidates),
                "--generation-parallel", "2", "--out", str(experiment), "--json"]

    def invoke(self, command: list[str], repo: Path, environment: dict[str, str]):
        return subprocess.run(command, cwd=repo, env=environment, text=True,
                              capture_output=True, timeout=30, check=False)

    def wait_for(self, predicate, process: subprocess.Popen) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if predicate():
                return
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail(f"controller exited before fixture checkpoint: {stdout}\n{stderr}")
            time.sleep(0.01)
        process.kill()
        stdout, stderr = process.communicate()
        self.fail(f"fixture checkpoint timed out: {stdout}\n{stderr}")

    def stop(self, experiment: Path, repo: Path, environment: dict[str, str]):
        stopped = self.invoke([str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI),
                               "stop", str(experiment), "--json"], repo, environment)
        self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)

    def test_busy_resume_returns_one_json_error_without_removing_owner_lock(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result, repo, experiment = fixtures.HillClimberTests.run_climb(self, root, "easy", apply=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            lock = experiment / "run.lock"
            owner = json.dumps({"pid": os.getpid(), "started_at": "fixture"})
            lock.write_text(owner)
            resumed = self.invoke([str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI),
                                   "resume", str(experiment), "--json"], repo, self.environment(root, "easy"))
            self.assertEqual(resumed.returncode, 4, resumed.stdout + resumed.stderr)
            self.assertEqual(len(resumed.stdout.strip().splitlines()), 1)
            self.assertEqual(json.loads(resumed.stdout)["error"]["code"], "E_BUSY")
            self.assertEqual(lock.read_text(), owner)

    def test_terminal_retained_resume_preserves_exit_status_and_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result, repo, experiment = fixtures.HillClimberTests.run_climb(self, root, "cheater", apply=False)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            ledger = (experiment / "events.jsonl").read_bytes()
            resumed = self.invoke([str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI),
                                   "resume", str(experiment), "--json"], repo, self.environment(root, "cheater"))
            self.assertEqual(resumed.returncode, 1, resumed.stdout + resumed.stderr)
            self.assertEqual(json.loads(resumed.stdout)["result"]["status"], "retained")
            self.assertEqual((experiment / "events.jsonl").read_bytes(), ledger)

    def test_completed_holdout_resume_restores_promotion_and_applies_once(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            experiment = root / "experiment"
            dirty = repo / "apply-blocker.txt"
            calls = root / "holdout-calls.txt"
            evaluator = root / "evaluate.py"
            evaluator.write_text(
                "import json, os\nfrom pathlib import Path\n"
                "phase = os.environ['HILL_CLIMBER_PHASE']\n"
                "candidate = os.environ['HILL_CLIMBER_CANDIDATE']\n"
                f"calls = Path({str(calls)!r})\n"
                "if phase == 'holdout':\n"
                "    with calls.open('a') as stream: stream.write(candidate + '\\n')\n"
                "    if candidate == 'holdout-candidate':\n"
                f"        Path({str(dirty)!r}).write_text('fail after holdout, before apply')\n"
                "print(json.dumps({'score': int(Path('solution.txt').read_text()), 'gates': {'valid': True}}))\n",
                encoding="utf-8")
            environment = self.environment(root, "easy")
            initial = self.invoke(self.command(repo, experiment, evaluator), repo, environment)
            self.assertEqual(initial.returncode, 2, initial.stdout + initial.stderr)
            self.assertEqual(json.loads(initial.stdout)["error"]["code"], "E_DIRTY")
            events = [json.loads(line) for line in (experiment / "events.jsonl").read_text().splitlines()]
            self.assertEqual(sum(event["type"] == "holdout_completed" for event in events), 1)
            dirty.unlink()
            resume = [str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI), "resume", str(experiment), "--json"]
            resumed = self.invoke(resume, repo, environment)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            receipt = json.loads(resumed.stdout)["result"]
            self.assertEqual(receipt["status"], "promoted")
            self.assertTrue(receipt["applied"])
            self.assertEqual((repo / "solution.txt").read_text().strip(), "5")
            repeated = self.invoke(resume, repo, environment)
            self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
            self.assertEqual(len(calls.read_text().splitlines()), 2)
            events = [json.loads(line) for line in (experiment / "events.jsonl").read_text().splitlines()]
            self.assertEqual(sum(event["type"] == "winner_applied" for event in events), 1)

    def test_receipt_only_resume_verifies_applied_tree_including_added_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            # A clone does not inherit local info/exclude. The legitimate new
            # file must still be checked when rebuilding the applied tree.
            with (repo / ".git/info/exclude").open("a") as stream:
                stream.write("\nnew.txt\n")
            experiment = root / "experiment"
            calls = root / "holdout-calls.txt"
            evaluator = root / "evaluate.py"
            evaluator.write_text(
                "import json,os\nfrom pathlib import Path\n"
                "candidate=os.environ['HILL_CLIMBER_CANDIDATE']\n"
                "if os.environ['HILL_CLIMBER_PHASE']=='holdout':\n"
                f"    with Path({str(calls)!r}).open('a') as stream: stream.write(candidate+'\\n')\n"
                "    if candidate=='holdout-candidate':\n"
                f"        Path({str(experiment / 'report.svg')!r}).mkdir()\n"
                "print(json.dumps({'score':int(Path('solution.txt').read_text()),'gates':{'valid':True}}))\n")
            sdk = root / "adding-sdk.mjs"
            sdk.write_text(
                f"import {{Codex as FakeCodex}} from {fixtures.FAKE_SDK.as_uri()!r};\n"
                "import {writeFileSync,readFileSync} from 'node:fs';\n"
                "import {join} from 'node:path';\n"
                "export class Codex extends FakeCodex { startThread(options) {\n"
                "const inner=super.startThread(options); return { async runStreamed(...args) {\n"
                "const stream=await inner.runStreamed(...args);\n"
                "writeFileSync(join(options.workingDirectory,'new.txt'),readFileSync(join(options.workingDirectory,'solution.txt')));\n"
                "return stream; } }; } }\n")
            environment = self.environment(root, "easy")
            environment["HILL_CLIMBER_CODEX_MODULE"] = str(sdk)
            command = self.command(repo, experiment, evaluator) + ["--mutable", "new.txt"]
            initial = self.invoke(command, repo, environment)
            self.assertEqual(initial.returncode, 2, initial.stdout + initial.stderr)
            self.assertEqual(json.loads(initial.stdout)["error"]["code"], "E_INTERNAL")
            self.assertTrue((repo / "new.txt").exists())
            self.assertTrue(json.loads((experiment / "state.json").read_text())["applied"])
            (experiment / "report.svg").rmdir()
            resume = [str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI), "resume", str(experiment), "--json"]
            # An unrelated source edit still blocks receipt-only recovery.
            (repo / "solution.txt").write_text("6\n")
            drifted = self.invoke(resume, repo, environment)
            self.assertEqual(json.loads(drifted.stdout)["error"]["code"], "E_DRIFT")
            (repo / "solution.txt").write_text("5\n")
            # Finished experiments need neither model auth nor SDK availability.
            (root / "bin/codex").write_text("#!/bin/sh\nexit 1\n")
            environment["HILL_CLIMBER_CODEX_MODULE"] = str(root / "missing-sdk.mjs")
            resumed = self.invoke(resume, repo, environment)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            receipt = json.loads(resumed.stdout)["result"]
            self.assertEqual(receipt["status"], "promoted")
            self.assertTrue(receipt["applied"])
            self.assertEqual((repo / "new.txt").read_text(), "5\n")
            self.assertEqual(fixtures.git(repo, "diff", "--cached"), "")
            self.assertEqual(len(calls.read_text().splitlines()), 2)
            events = [json.loads(line) for line in (experiment / "events.jsonl").read_text().splitlines()]
            self.assertEqual(sum(event["type"] == "winner_applied" for event in events), 1)

    def test_interruption_keeps_lock_until_every_generation_worker_settles(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            experiment = root / "experiment"
            ready = root / "ready"
            lock_observation = root / "lock-observation.json"
            sdk = root / "slow-cancellation.mjs"
            sdk.write_text(
                "import {existsSync,writeFileSync,mkdirSync} from 'node:fs';\n"
                "export class Codex { startThread(options) { return {\n"
                " async runStreamed(prompt,{signal}) {\n"
                "  const index=Number(prompt.match(/candidate (\\d+)\\//i)[1]);\n"
                f"  mkdirSync({str(ready)!r}, {{recursive:true}});\n"
                f"  writeFileSync({str(ready)!r}+'/'+index,'ready');\n"
                "  await new Promise((resolve,reject)=>{\n"
                "   const keepAlive=setTimeout(()=>reject(new Error('fixture timeout')),30000);\n"
                "   signal.addEventListener('abort',()=>{\n"
                "    clearTimeout(keepAlive);\n"
                "    if(index===1) reject(new Error('aborted'));\n"
                "    else setTimeout(()=>{\n"
                f"     writeFileSync({str(lock_observation)!r},JSON.stringify({{locked:existsSync({str(experiment / 'run.lock')!r})}}));\n"
                "     reject(new Error('aborted'));\n"
                "    },200);\n"
                "   },{once:true});\n"
                "  });\n"
                " } }; } }\n", encoding="utf-8")
            evaluator = root / "evaluate.py"
            evaluator.write_text("import json\nprint(json.dumps({'score':0,'gates':{'valid':True}}))\n")
            environment = self.environment(root, "easy")
            environment["HILL_CLIMBER_CODEX_MODULE"] = str(sdk)
            process = subprocess.Popen(self.command(repo, experiment, evaluator), cwd=repo,
                                       env=environment, text=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            try:
                self.wait_for(lambda: (ready / "1").exists() and (ready / "2").exists(), process)
                self.stop(experiment, repo, environment)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 130, stdout + stderr)
                self.assertTrue(json.loads(lock_observation.read_text())["locked"],
                                "controller released the writer lock before sibling cancellation completed")
                self.assertFalse((experiment / "run.lock").exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_evaluation_failure_is_terminal_across_interrupted_round_resume(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            experiment = root / "experiment"
            waiting = root / "waiting"
            released = root / "released"
            calls = root / "failed-calls.txt"
            evaluator = root / "evaluate.py"
            evaluator.write_text(
                "import json,os,time\nfrom pathlib import Path\n"
                "candidate=os.environ['HILL_CLIMBER_CANDIDATE']\n"
                "phase=os.environ['HILL_CLIMBER_PHASE']\n"
                "if phase=='development' and candidate=='r01-c01':\n"
                f"    with Path({str(calls)!r}).open('a') as stream: stream.write('failed\\n')\n"
                "    raise SystemExit(7)\n"
                f"if phase=='development' and candidate=='r01-c02' and not Path({str(released)!r}).exists():\n"
                f"    Path({str(waiting)!r}).write_text('waiting')\n"
                "    time.sleep(30)\n"
                "print(json.dumps({'score':int(Path('solution.txt').read_text()),'gates':{'valid':True}}))\n",
                encoding="utf-8")
            environment = self.environment(root, "easy")
            process = subprocess.Popen(self.command(repo, experiment, evaluator), cwd=repo,
                                       env=environment, text=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            try:
                self.wait_for(waiting.exists, process)
                self.stop(experiment, repo, environment)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 130, stdout + stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            (experiment / "stop.request").unlink()
            released.write_text("resume")
            resumed = self.invoke([str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI),
                                   "resume", str(experiment), "--json"], repo, environment)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            self.assertEqual(calls.read_text().splitlines(), ["failed"],
                             "generated.json resurrected an already failed evaluation")
            receipt = json.loads(resumed.stdout)["result"]
            self.assertEqual(receipt["counts"]["candidates"], 2)
            self.assertEqual(receipt["counts"]["crashed"], 1)
            self.assertEqual(receipt["usage"]["input_tokens"], 40)

    def test_resume_rejects_tampered_generated_and_evaluated_artifacts(self):
        for artifact in ("generated", "result"):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                repo = self.make_repo(root)
                experiment = root / "experiment"
                waiting = root / "waiting"
                evaluator = root / "evaluate.py"
                evaluator.write_text(
                    "import json,os,time\nfrom pathlib import Path\n"
                    "if os.environ['HILL_CLIMBER_PHASE']=='development' and os.environ['HILL_CLIMBER_CANDIDATE']=='r01-c02':\n"
                    f"    Path({str(waiting)!r}).write_text('waiting')\n"
                    "    time.sleep(30)\n"
                    "print(json.dumps({'score':int(Path('solution.txt').read_text()),'gates':{'valid':True}}))\n",
                    encoding="utf-8")
                environment = self.environment(root, "easy")
                process = subprocess.Popen(self.command(repo, experiment, evaluator), cwd=repo,
                                           env=environment, text=True, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
                try:
                    self.wait_for(waiting.exists, process)
                    self.stop(experiment, repo, environment)
                    stdout, stderr = process.communicate(timeout=15)
                    self.assertEqual(process.returncode, 130, stdout + stderr)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
                (experiment / "stop.request").unlink()
                candidate = "r01-c02" if artifact == "generated" else "r01-c01"
                path = experiment / "candidates" / candidate / f"{artifact}.json"
                data = json.loads(path.read_text())
                if artifact == "generated":
                    data["metadata"]["mechanism"] = "altered after generation"
                else:
                    data["evaluation"]["score"] = 999
                path.write_text(json.dumps(data), encoding="utf-8")
                resumed = self.invoke([str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI),
                                       "resume", str(experiment), "--json"], repo, environment)
                self.assertEqual(resumed.returncode, 3, resumed.stdout + resumed.stderr)
                self.assertEqual(json.loads(resumed.stdout)["error"]["code"], "E_EVIDENCE")
                self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")
                events = [json.loads(line) for line in (experiment / "events.jsonl").read_text().splitlines()]
                self.assertFalse(any(event["type"] == "holdout_started" for event in events))

    def test_recovery_stop_and_expired_wall_budget_never_launch_missing_candidates(self):
        for reason in ("stop_requested", "wall_budget_exhausted"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                repo = self.make_repo(root)
                experiment = root / "experiment"
                evaluator = root / "evaluate.py"
                evaluator.write_text("import json\nprint(json.dumps({'score':0,'gates':{'valid':True}}))\n")
                environment = self.environment(root, "easy")
                environment["HILL_CLIMBER_FAKE_DELAY_MS"] = "10000"
                command = self.command(repo, experiment, evaluator)
                if reason == "wall_budget_exhausted":
                    command += ["--max-wall-seconds", "1"]
                process = subprocess.Popen(command, cwd=repo, env=environment, text=True,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    ledger = experiment / "events.jsonl"
                    self.wait_for(lambda: ledger.exists() and '"type":"candidate_started"' in ledger.read_text(), process)
                    self.stop(experiment, repo, environment)
                    stdout, stderr = process.communicate(timeout=15)
                    self.assertEqual(process.returncode, 130, stdout + stderr)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
                before = [json.loads(line) for line in ledger.read_text().splitlines()]
                if reason == "wall_budget_exhausted":
                    (experiment / "stop.request").unlink()
                    created = json.loads((experiment / "manifest.json").read_text())["created_at"]
                    remaining = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() + 1.05 - time.time()
                    if remaining > 0:
                        time.sleep(remaining)
                resumed = self.invoke([str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI),
                                       "resume", str(experiment), "--json"], repo,
                                      self.environment(root, "easy"))
                self.assertEqual(resumed.returncode, 1, resumed.stdout + resumed.stderr)
                receipt = json.loads(resumed.stdout)["result"]
                self.assertEqual(receipt["terminal_reason"], reason)
                self.assertEqual(receipt["counts"]["candidates"], 0)
                after = [json.loads(line) for line in ledger.read_text().splitlines()]
                self.assertEqual(sum(event["type"] == "candidate_started" for event in after),
                                 sum(event["type"] == "candidate_started" for event in before))

    def test_legacy_interrupted_experiment_preserves_evaluation_time_usage_accounting(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = self.make_repo(root)
            experiment = root / "experiment"
            legacy = root / "legacy-controller"
            for filename in ("bin/hill-climber", "scripts/hill_climber.mjs"):
                destination = legacy / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                content = (fixtures.ROOT / filename).read_text()
                if filename.endswith(".mjs"):
                    # Legacy experiments omit the opt-in accounting version.
                    # Generate that valid persisted shape through the controller
                    # rather than modifying its hashed manifest or ledger later.
                    accounting = '    usage_accounting: "generation",\n'
                    self.assertEqual(content.count(accounting), 1)
                    content = content.replace(accounting, "")
                destination.write_text(content)
            (legacy / "node_modules").symlink_to(fixtures.ROOT / "node_modules", target_is_directory=True)
            waiting = root / "waiting"
            released = root / "released"
            evaluator = root / "evaluate.py"
            evaluator.write_text(
                "import json,os,time\nfrom pathlib import Path\n"
                f"if os.environ['HILL_CLIMBER_PHASE']=='development' and os.environ['HILL_CLIMBER_CANDIDATE']=='r01-c02' and not Path({str(released)!r}).exists():\n"
                f"    Path({str(waiting)!r}).write_text('waiting')\n"
                "    time.sleep(30)\n"
                "print(json.dumps({'score':int(Path('solution.txt').read_text()),'gates':{'valid':True}}))\n",
                encoding="utf-8")
            environment = self.environment(root, "easy")
            command = self.command(repo, experiment, evaluator)
            command[1] = str(legacy / "bin/hill-climber")
            process = subprocess.Popen(command, cwd=repo, env=environment, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                self.wait_for(waiting.exists, process)
                self.stop(experiment, repo, environment)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 130, stdout + stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            manifest = json.loads((experiment / "manifest.json").read_text())
            self.assertNotIn("usage_accounting", manifest["config"])
            state = json.loads((experiment / "state.json").read_text())
            self.assertEqual(state["usage"]["input_tokens"], 20)
            (experiment / "stop.request").unlink()
            released.write_text("resume")
            resumed = self.invoke([str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI),
                                   "resume", str(experiment), "--json"], repo, environment)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            receipt = json.loads(resumed.stdout)["result"]
            self.assertEqual(receipt["counts"]["candidates"], 2)
            self.assertEqual(receipt["usage"]["input_tokens"], 40)
            self.assertEqual(receipt["usage"]["output_tokens"], 20)


if __name__ == "__main__":
    unittest.main()
