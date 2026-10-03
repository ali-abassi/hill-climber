"""Run isolated adversarial cases through the real CLI and a synthetic SDK.

Every repository, login executable, evaluator, and SDK session lives in a fresh
temporary directory. The fixture never imports a provider or external grader.
"""

from __future__ import annotations

import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


SDK = r'''import {writeFileSync, renameSync, mkdirSync, rmSync, chmodSync} from 'node:fs';
import {join, dirname} from 'node:path';
import {spawnSync} from 'node:child_process';

const spec = SPEC;

export class Codex {
  startThread(options) {
    return {
      async runStreamed() {
        const cwd = options.workingDirectory;
        writeFileSync(join(cwd, 'solution.txt'), '1\n');
        for (const path of spec.extra_paths ?? []) {
          mkdirSync(dirname(join(cwd, path)), {recursive: true});
          writeFileSync(join(cwd, path), 'forbidden\n');
        }
        if (spec.rename) {
          renameSync(join(cwd, spec.rename[0]), join(cwd, spec.rename[1]));
          spawnSync('git', ['add', '-A'], {cwd});
        }
        if (spec.self_commit) {
          writeFileSync(join(cwd, spec.self_commit), 'forbidden\n');
          spawnSync('git', ['add', '-A'], {cwd});
          const result = spawnSync('git', [
            '-c', 'user.name=Candidate', '-c', 'user.email=candidate@example.test',
            'commit', '-qm', 'unauthorized candidate commit'
          ], {cwd});
          if (result.status !== 0) throw new Error('synthetic self-commit failed');
          writeFileSync(join(cwd, 'solution.txt'), '2\n');
        }
        if (spec.content !== undefined) {
          writeFileSync(join(cwd, 'solution.txt'), spec.content);
        }
        if (spec.gitdir_attack) {
          rmSync(join(cwd, '.git'), {recursive: true, force: true});
          spawnSync('git', ['init', '-q'], {cwd});
          const hooks = join(cwd, '.git', 'hostile-hooks');
          mkdirSync(hooks, {recursive: true});
          const script = '#\x21/bin/sh\nprintf observed > ' + JSON.stringify(spec.marker) + '\n';
          const hook = join(hooks, 'pre-commit');
          writeFileSync(hook, script);
          chmodSync(hook, 0o755);
          const fsmonitor = join(hooks, 'monitor');
          writeFileSync(fsmonitor, script);
          chmodSync(fsmonitor, 0o755);
          spawnSync('git', ['config', 'core.hooksPath', hooks], {cwd});
          spawnSync('git', ['config', 'core.fsmonitor', fsmonitor], {cwd});
        }

        async function* events() {
          yield {type: 'thread.started', thread_id: 'adversarial-' + spec.id};
          for (const event of spec.before_events ?? []) yield event;
          if (spec.busy_ms) {
            const end = performance.now() + spec.busy_ms;
            while (performance.now() < end) {
              const pause = performance.now() + .25;
              while (performance.now() < pause) {}
              yield {type: 'item.updated', item: {type: 'reasoning', text: 'bounded'}};
            }
          }
          for (let i = 0; i < (spec.pressure_count ?? 0); i++) {
            yield {
              type: 'item.updated',
              item: {
                type: 'command_execution',
                aggregated_output: 'x'.repeat(spec.pressure_bytes ?? 1024)
              }
            };
          }
          yield {
            type: 'item.completed',
            item: {
              type: 'agent_message',
              text: spec.response ?? JSON.stringify({
                mechanism: 'panel-control',
                hypothesis: 'Improve a synthetic value.',
                summary: 'Synthetic provider.'
              })
            }
          };
          const valid = {input_tokens: 11, output_tokens: 7, cached_input_tokens: 2};
          for (const usage of spec.meters ?? [valid]) {
            yield {type: 'turn.completed', usage};
          }
          for (const event of spec.after_events ?? []) yield event;
        }
        return {events: events()};
      }
    };
  }
}
'''


def one_json(result: subprocess.CompletedProcess[str]) -> dict:
    """Require exactly one machine-readable document on standard output."""
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1, (
        f"Expected one JSON line, exit={result.returncode}: "
        f"stdout={result.stdout[:1000]!r}, stderr={result.stderr[-1000:]!r}"
    )
    document = json.loads(lines[0])
    assert isinstance(document, dict), "CLI JSON response must be an object"
    return document


def run_case(source: Path, case: dict) -> None:
    """Assert a public execution contract without touching existing sessions."""
    with tempfile.TemporaryDirectory(prefix="hill-adversarial-contract-") as raw:
        temporary = Path(raw)
        repo = temporary / "repo"
        repo.mkdir()

        def git(*args: str) -> str:
            result = subprocess.run(
                ["git", *args], cwd=repo, text=True, capture_output=True, check=True
            )
            return result.stdout.strip()

        git("init", "-q")
        git("config", "user.name", "Synthetic Contract")
        git("config", "user.email", "contract@example.test")
        (repo / "solution.txt").write_text("0\n", encoding="utf-8")
        (repo / "protected.txt").write_text("preserve\n", encoding="utf-8")
        for path in case.get("initial_paths", []):
            destination = repo / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("initial\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "baseline")
        head = git("rev-parse", "HEAD")

        bindir = temporary / "bin"
        bindir.mkdir()
        binary = bindir / "codex"
        binary.write_text(
            "#!/bin/sh\nprintf '%s\\n' 'Logged in using ChatGPT'\n", encoding="utf-8"
        )
        binary.chmod(0o755)
        marker = temporary / "outside-marker"
        sdk = temporary / "provider.mjs"
        specification = {**case, "marker": str(marker)}
        sdk.write_text(
            SDK.replace("SPEC", json.dumps(specification, ensure_ascii=False)),
            encoding="utf-8",
        )

        evaluator_code = (
            "import json, os\n"
            "from pathlib import Path\n"
            f"case = {case!r}\n"
            "value = int(Path('solution.txt').read_text())\n"
            "values = case.get('mean_values')\n"
            "score = (values[int(os.environ['HILL_CLIMBER_SEED']) - 42] "
            "if value and values else "
            "(value if value else case.get('baseline_score', value)))\n"
            "gates = case.get('candidate_gates', {'valid': True}) "
            "if value else {'valid': True}\n"
            "print(json.dumps({'score': score, 'gates': gates, "
            "'feedback': ['synthetic case']}))\n"
        )
        development = temporary / "development.py"
        synthetic_holdout = temporary / "synthetic_holdout.py"
        development.write_text(evaluator_code, encoding="utf-8")
        synthetic_holdout.write_text(evaluator_code, encoding="utf-8")
        experiment = temporary / "experiment"
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith(("HILL_CLIMBER_", "PAL_")):
                environment.pop(key)
        environment.update(
            PATH=str(bindir) + os.pathsep + environment["PATH"],
            HILL_CLIMBER_CODEX_MODULE=str(sdk),
            PYTHONDONTWRITEBYTECODE="1",
        )
        if case.get("heap_mb"):
            environment["NODE_OPTIONS"] = f"--max-old-space-size={case['heap_mb']}"

        repeats = len(case.get("mean_values", [0]))
        command = [
            sys.executable, str(source / "bin/hill-climber"), "run", "--json",
            "--workspace", str(repo), "--task", "Improve a synthetic value",
            "--eval", shlex.join([sys.executable, str(development)]),
            "--holdout-eval", shlex.join([sys.executable, str(synthetic_holdout)]),
            "--candidates", "1", "--rounds", "1", "--generation-parallel", "1",
            "--candidate-timeout", "1", "--eval-timeout", "4",
            "--max-wall-seconds", "25", "--max-failures", "1",
            "--repeats", str(repeats), "--holdout-repeats", str(repeats),
            "--out", str(experiment), "--no-apply",
        ]
        for path in case.get("mutable", ["solution.txt"]):
            command.extend(["--mutable", path])
        result = subprocess.run(
            command, cwd=repo, env=environment, text=True, capture_output=True, timeout=15
        )
        response = one_json(result)
        receipt = response.get("result", {})
        state = json.loads((experiment / "state.json").read_text(encoding="utf-8"))

        assert git("rev-parse", "HEAD") == head, "Source HEAD changed despite --no-apply"
        assert git("status", "--porcelain") == "", "Source worktree changed"
        assert (repo / "solution.txt").read_text(encoding="utf-8") == "0\n"
        assert (repo / "protected.txt").read_text(encoding="utf-8") == "preserve\n"
        assert not (experiment / "run.lock").exists(), "Writer lock leaked"
        assert not marker.exists(), "Candidate-controlled Git hook or fsmonitor executed"
        for name, value in state["usage"].items():
            assert isinstance(value, (int, float)) and not isinstance(value, bool), name
            assert math.isfinite(value) and value >= 0, f"Invalid aggregate usage: {name}"

        expected = case["expected"]
        if expected == "promoted":
            assert result.returncode == 0, f"Valid candidate failed: {response}"
            assert receipt["status"] == "promoted", "Valid candidate was not promoted"
            if case.get("immutable_parent"):
                generated = json.loads(
                    (experiment / "candidates/r01-c01/generated.json").read_text(encoding="utf-8")
                )
                ancestry = subprocess.run(
                    ["git", "rev-list", "--parents", "-n", "1", generated["commit"]],
                    cwd=experiment / "repo", text=True, capture_output=True, check=True,
                ).stdout.split()
                assert ancestry == [generated["commit"], head], "Candidate commit lost immutable parent"
        elif expected == "retained_gate":
            assert result.returncode == 1, "Failed gate returned success"
            assert receipt["status"] == "retained", "Failed gate candidate was promoted"
            assert receipt["promotion"]["holdout_used"] is False, "Failed gate reached holdout"
            evaluation = json.loads(
                (experiment / "evaluations/r01-c01/development/aggregate.json")
                .read_text(encoding="utf-8")
            )
            if "__proto__" in case.get("candidate_gates", {}):
                assert evaluation["gates"].get("__proto__") is False, "False gate was lost"
            else:
                assert not evaluation["gates_passed"], "False gate passed"
        else:
            assert result.returncode == 1, f"Invalid candidate returned wrong exit: {response}"
            assert receipt.get("status") == "retained", "Invalid candidate was promoted"
            candidate = experiment / "candidates/r01-c01"
            assert not (candidate / "generated.json").exists(), "Invalid completion published"
            assert receipt["promotion"]["holdout_used"] is False, "Invalid completion reached holdout"
            failure = json.loads((candidate / "failure.json").read_text(encoding="utf-8"))
            assert failure["code"] in case.get("allowed_codes", [expected]), (
                f"Expected {case.get('allowed_codes', [expected])}, got {failure['code']}"
            )

        if "mean_values" in case and expected == "promoted":
            score = receipt["incumbent"]["score"]
            wanted = sum(value / len(case["mean_values"]) for value in case["mean_values"])
            assert isinstance(score, (int, float)) and math.isfinite(score), "Mean overflowed"
            assert math.isclose(score, wanted, rel_tol=1e-12, abs_tol=1e-12), "Mean changed"
            for path in experiment.glob("evaluations/*/*/aggregate.json"):
                aggregate = json.loads(path.read_text(encoding="utf-8"))
                assert isinstance(aggregate["score"], (int, float))
                assert math.isfinite(aggregate["score"]), f"Nonfinite durable score: {path.name}"
            chart = (experiment / "report.svg").read_text(encoding="utf-8")
            assert "NaN" not in chart and "Infinity" not in chart, "Nonfinite SVG coordinates"
        if case.get("meter_retained"):
            assert state["usage"]["input_tokens"] == 11, "Known input meter lost or duplicated"
            assert state["usage"]["output_tokens"] == 7, "Known output meter lost or duplicated"
        if case.get("trace_limit"):
            trace = experiment / "candidates/r01-c01/turn.json"
            assert trace.exists(), "Received trace missing"
            assert trace.stat().st_size <= case["trace_limit"], "Received trace exceeded limit"

        status = subprocess.run(
            [sys.executable, str(source / "bin/hill-climber"), "status", str(experiment), "--json"],
            cwd=repo, env=environment, text=True, capture_output=True, timeout=5,
        )
        status_document = one_json(status)
        assert status.returncode == 0 and status_document["ok"], "Evidence not inspectable"

        if case.get("receipt_tamper"):
            target = experiment / "receipt.json"
            data = json.loads(target.read_text(encoding="utf-8"))
            keys = case["receipt_tamper"].split(".")
            cursor = data
            for key in keys[:-1]:
                cursor = cursor[key]
            value = cursor[keys[-1]]
            cursor[keys[-1]] = value + 13 if isinstance(value, (int, float)) else f"forged-{value}"
            target.write_text(json.dumps(data), encoding="utf-8")
            for action in ("inspect", "resume"):
                observed = subprocess.run(
                    [sys.executable, str(source / "bin/hill-climber"), action, str(experiment), "--json"],
                    cwd=repo, env=environment, text=True, capture_output=True, timeout=8,
                )
                parsed = one_json(observed)
                assert observed.returncode != 0, f"Tampered receipt accepted by {action}"
                assert parsed.get("error", {}).get("code") == "E_EVIDENCE", (
                    f"Tampered receipt misclassified by {action}: {parsed}"
                )
            assert not (experiment / "run.lock").exists(), "Rejected resume leaked writer lock"
            assert git("rev-parse", "HEAD") == head and git("status", "--porcelain") == ""
