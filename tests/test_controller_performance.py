from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from tests import test_hill_climber as fixtures


class ControllerPerformanceTests(unittest.TestCase):
    make_repo = fixtures.HillClimberTests.make_repo
    environment = fixtures.HillClimberTests.environment

    def climb(self, root: Path, code: str, *flags: str, sdk: Path | None = None):
        repo = self.make_repo(root)
        evaluator = root / "evaluate.py"
        evaluator.write_text(code, encoding="utf-8")
        argv = shlex.join([str(fixtures.PRODUCT_PYTHON), str(evaluator)])
        experiment = root / "experiment"
        command = [str(fixtures.PRODUCT_PYTHON), str(fixtures.CLI), "run",
                   "--workspace", str(repo), "--task", "Improve the integer score",
                   "--eval", argv, "--holdout-eval", argv,
                   "--mutable", "solution.txt", "--candidates", "5",
                   "--out", str(experiment), "--json", "--no-apply", *flags]
        environment = self.environment(root, "easy")
        if sdk:
            environment["HILL_CLIMBER_CODEX_MODULE"] = str(sdk)
        result = subprocess.run(command, cwd=repo, env=environment,
                                text=True, capture_output=True, timeout=45, check=False)
        self.assertEqual(len(result.stdout.strip().splitlines()), 1, result.stdout + result.stderr)
        return result, repo, experiment

    def test_parallel_grading_is_bounded_and_keeps_seeded_repeats_and_winner(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            markers = root / "markers"
            markers.mkdir()
            intervals = root / "intervals"
            intervals.mkdir()
            # Each of the first three graders waits for all three to enter.
            # Serial grading cannot pass this barrier; no timing speed threshold
            # is used to assert concurrency.
            code = (
                "import json,os,time\nfrom pathlib import Path\n"
                "candidate=os.environ['HILL_CLIMBER_CANDIDATE']\n"
                "phase=os.environ['HILL_CLIMBER_PHASE']\n"
                "seed=os.environ['HILL_CLIMBER_SEED']\n"
                f"markers=Path({str(markers)!r})\n"
                "if phase=='development' and candidate!='baseline':\n"
                "    started=time.monotonic_ns()\n"
                "    (markers/(candidate+'-'+seed)).write_text('started')\n"
                "    if seed=='42' and candidate in ['r01-c01','r01-c02','r01-c03']:\n"
                "        deadline=time.monotonic()+10\n"
                "        while len(list(markers.glob('*-42')))<3:\n"
                "            if time.monotonic()>deadline: raise SystemExit(7)\n"
                "            time.sleep(.005)\n"
                f"    (Path({str(intervals)!r})/(candidate+'-'+seed)).write_text(json.dumps([started,time.monotonic_ns()]))\n"
                "print(json.dumps({'score':int(Path('solution.txt').read_text()),'gates':{'valid':True},"
                "'feedback':['Fix the general integer mechanism, not individual cases.']}))\n"
            )
            result, repo, experiment = self.climb(root, code, "--evaluation-parallel", "3", "--repeats", "2")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)["result"]
            self.assertEqual(receipt["incumbent"]["id"], "r01-c02")
            self.assertEqual(receipt["counts"]["candidates"], 5)
            self.assertEqual(receipt["counts"]["crashed"], 0)
            self.assertEqual(receipt["usage"]["input_tokens"], 100)
            self.assertEqual(len(list(markers.iterdir())), 10)
            boundaries = []
            for path in intervals.iterdir():
                started, finished = json.loads(path.read_text())
                boundaries.extend([(started, 1), (finished, -1)])
            active = peak = 0
            for _, delta in sorted(boundaries):
                active += delta
                peak = max(peak, active)
            self.assertEqual(peak, 3)
            for candidate in range(1, 6):
                path = experiment / "evaluations" / f"r01-c{candidate:02}" / "development"
                repeats = [json.loads((path / f"repeat-{i}.json").read_text()) for i in (1, 2)]
                self.assertEqual([item["seed"] for item in repeats], [42, 43])
            prompt = (experiment / "candidates/r01-c01/prompt.txt").read_text()
            self.assertIn("baseline: score=0", prompt)
            self.assertIn("Fix the general integer mechanism", prompt)
            self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")
            fixtures.HillClimberTests.assert_ledger_chain(self, experiment)

    def test_chunked_unicode_output_at_limit_is_preserved_exactly(self):
        with tempfile.TemporaryDirectory() as raw:
            code = (
                "import json,os,sys\nfrom pathlib import Path\n"
                "payload=('🙂'.encode()*524288)\n"
                "for offset in range(0,len(payload),4093):\n"
                "    os.write(2,payload[offset:offset+4093])\n"
                "print(json.dumps({'score':int(Path('solution.txt').read_text()),'gates':{'valid':True}}))\n"
            )
            result, _, experiment = self.climb(Path(raw), code, "--candidates", "1")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            captured = (experiment / "evaluations/baseline/development/repeat-1.stderr").read_bytes()
            self.assertEqual(len(captured), 2 * 1024 * 1024)
            self.assertEqual(captured.decode(), "🙂" * 524288)

    def test_output_overflow_fails_closed_with_machine_error(self):
        with tempfile.TemporaryDirectory() as raw:
            result, repo, experiment = self.climb(Path(raw), "import os\nos.write(1,b'x'*(2*1024*1024+1))\n")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["error"]["code"], "E_OUTPUT_LIMIT")
            self.assertFalse((experiment / "candidates").exists())
            self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")

    def test_all_generated_usage_is_counted_when_grading_stops_early(self):
        with tempfile.TemporaryDirectory() as raw:
            code = (
                "import json,os\n"
                "if os.environ['HILL_CLIMBER_CANDIDATE']!='baseline': raise SystemExit(7)\n"
                "print(json.dumps({'score':0,'gates':{'valid':True}}))\n"
            )
            result, _, experiment = self.climb(Path(raw), code, "--max-failures", "1")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)["result"]
            self.assertEqual(receipt["counts"]["crashed"], 1)
            self.assertEqual(receipt["usage"]["input_tokens"], 100)
            self.assertEqual(receipt["usage"]["output_tokens"], 50)
            self.assertEqual(receipt["terminal_reason"], "failure_budget_exhausted")
            self.assertEqual(len(list((experiment / "candidates").glob("*/generated.json"))), 5)

    def test_malformed_metered_turns_keep_trace_usage_and_stop_new_generation(self):
        for response in ("invalid JSON", "null", "[]"):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                sdk = root / "malformed-sdk.mjs"
                sdk.write_text(
                    "export class Codex { startThread() { return { async runStreamed() {\n"
                    "async function* events() {\n"
                    "yield {type:'thread.started',thread_id:'metered'};\n"
                    f"yield {{type:'item.completed',item:{{type:'agent_message',text:{json.dumps(response)}}}}};\n"
                    "yield {type:'turn.completed',usage:{input_tokens:20,output_tokens:10}};\n"
                    "} return {events:events()}; } }; } }\n")
                code = "import json\nprint(json.dumps({'score':0,'gates':{'valid':True}}))\n"
                result, _, experiment = self.climb(root, code, "--max-failures", "1", sdk=sdk)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                receipt = json.loads(result.stdout)["result"]
                self.assertEqual(receipt["counts"]["invalid"], 2)
                self.assertEqual(receipt["counts"]["candidates"], 2)
                self.assertEqual(receipt["usage"]["input_tokens"], 40)
                self.assertEqual(receipt["usage"]["output_tokens"], 20)
                traces = list((experiment / "candidates").glob("*/turn.json"))
                self.assertEqual(len(traces), 2)
                self.assertTrue(all(json.loads(path.read_text())["usage"]["input_tokens"] == 20 for path in traces))

    @unittest.skipIf(os.name == "nt", "POSIX process group shutdown")
    def test_timeout_kills_descendant_even_after_parent_closes_stdio(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            survivor = root / "survived"
            pidfile = root / "descendant.pid"
            child = root / "descendant.py"
            child.write_text(
                "import signal,time\nfrom pathlib import Path\n"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                f"Path({str(pidfile)!r}).write_text(str(__import__('os').getpid()))\n"
                "time.sleep(2)\n"
                f"Path({str(survivor)!r}).write_text('orphan survived')\n"
            )
            code = (
                "import subprocess,sys,time\n"
                f"subprocess.Popen([sys.executable,{str(child)!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                "time.sleep(30)\n"
            )
            try:
                result, _, _ = self.climb(root, code, "--eval-timeout", "1")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["error"]["code"], "E_TIMEOUT")
                self.assertTrue(pidfile.exists(), "descendant fixture never started")
                time.sleep(1.3)
                self.assertFalse(survivor.exists(), "timed-out evaluator left its child alive")
            finally:
                if pidfile.exists():
                    try:
                        os.kill(int(pidfile.read_text()), 9)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
