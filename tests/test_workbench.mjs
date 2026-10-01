import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createHash } from "node:crypto";
import { request as httpRequest } from "node:http";
import { createWorkbenchServer, buildPlan, recipes, inspectExperiment, runProgram } from "../scripts/workbench.mjs";

const valid = { recipe: "code", workspace: "/tmp/source repo", task: "Improve edge cases", eval: "python3 /tmp/development.py", holdoutEval: "python3 /tmp/private.py", mutable: "src/**/*.py\nsrc/**/*.js", out: "/tmp/experiment result" };

test("all task recipes produce bounded faithful CLI arguments, safely quoting hostile text", () => {
  for (const recipe of recipes) {
    const input = { ...valid, recipe: recipe.id, task: "Preserve café 'quotes'; $(touch /tmp/should-never-exist) `uname`\nsecond line", details: "A < B & JSON stays data", model: "chosen-model" };
    const plan = buildPlan(input);
    const parsed = spawnSync("python3", ["-c", "import json,shlex,sys; print(json.dumps(shlex.split(sys.argv[1])))", plan.command], { encoding: "utf8" });
    assert.equal(parsed.status, 0);
    const argv = JSON.parse(parsed.stdout);
    const value = (key) => argv.find((arg) => arg.startsWith(`${key}=`))?.slice(key.length + 1);
    assert.equal(value("--task"), input.task);
    assert.equal(value("--details"), input.details);
    assert.equal(value("--workspace"), input.workspace);
    assert.equal(value("--holdout-eval"), input.holdoutEval);
    assert.equal(value("--repeats"), String(recipe.repeats));
    assert.equal(value("--model"), "chosen-model");
    assert.equal(argv.filter((arg) => arg.startsWith("--mutable=")).length, 2);
    assert.equal(argv.at(-1), "--no-apply");
    assert.equal(plan.maxAttempts, 3);
    assert.match(plan.brief, /one-time unseen holdout/);
    const parserScript = "import json,runpy,sys; m=runpy.run_path(sys.argv[1]); args=m['build_parser']().parse_args(json.load(sys.stdin)); print(json.dumps(m['request_from'](args)))";
    const parsedRequest = spawnSync("python3", ["-c", parserScript, argv[1]], { input: JSON.stringify(argv.slice(2)), encoding: "utf8" });
    assert.equal(parsedRequest.status, 0, parsedRequest.stderr);
    assert.equal(JSON.parse(parsedRequest.stdout).task, input.task);
  }
});

test("leading dash objective/details survive the real CLI parser and malformed argv is refused", () => {
  const plan = buildPlan({ ...valid, task: "--help", details: "-preserve" });
  const source = "import json,runpy,shlex,sys; argv=shlex.split(sys.argv[1]); m=runpy.run_path(argv[1]); args=m['build_parser']().parse_args(argv[2:]); print(json.dumps(m['request_from'](args)))";
  const result = spawnSync("python3", ["-c", source, plan.command], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).task, "--help");
  assert.equal(JSON.parse(result.stdout).details, "-preserve");
  assert.throws(() => buildPlan({ ...valid, eval: "python3 'unclosed" }), /command syntax/);
});

test("invalid paths, task families, budgets and mutable surfaces are rejected", () => {
  const invalid = [null, [], {}, { recipe: "magic" }, { workspace: "." }, { out: "/tmp/source repo/evidence" }, { mutable: "../private/*" }, { mutable: "!secret" }, { mutable: "/tmp/src" }, { task: "" }, { maxTokens: -1 }, { candidates: 21 }, { rounds: 1.5 }, { minGain: "NaN" }, { repeats: null }, { reasoning: "automatic" }, { details: "\0secret" }, { evaluationParallel: 9 }];
  for (const item of invalid) assert.throws(() => buildPlan(item === null || Array.isArray(item) ? item : { ...valid, ...item, ...(Object.keys(item).length === 0 ? { task: "" } : {}) }));
  const warning = buildPlan({ ...valid, recipe: "performance", holdoutEval: valid.eval, mutable: "**/*", evaluationParallel: 5, repeats: 1 });
  assert.ok(warning.warnings.some((text) => text.includes("identical")));
  assert.ok(warning.warnings.some((text) => text.includes("noise floor")));
  assert.ok(warning.warnings.some((text) => text.includes("independent graders")));
});

test("timed-out inspection reaps its subprocess group even with detached stdio", { skip: process.platform === "win32" }, async () => {
  const root = mkdtempSync(join(tmpdir(), "hill-workbench-timeout-"));
  const pidPath = join(root, "descendant.pid");
  try {
    const source = `const {spawn}=require('node:child_process'); const {writeFileSync}=require('node:fs'); const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore'}); writeFileSync(process.argv[1],String(child.pid)); setInterval(()=>{},1000);`;
    await assert.rejects(runProgram(process.execPath, ["-e", source, pidPath], { timeout: 1500 }), /timed out/);
    const pid = Number(readFileSync(pidPath, "utf8"));
    let state = "";
    for (let index = 0; index < 50; index += 1) {
      state = spawnSync("ps", ["-o", "stat=", "-p", String(pid)], { encoding: "utf8" }).stdout.trim();
      if (!state || state.startsWith("Z")) break;
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    assert.ok(!state || state.startsWith("Z"), `descendant ${pid} still running: ${state}`);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("loopback server guards origins, limits payloads, and verifies genuine demo evidence", async () => {
  const server = createWorkbenchServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const request = (path, body, headers = {}) => fetch(base + path, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });
    const recipesResponse = await fetch(base + "/api/recipes");
    assert.equal(recipesResponse.status, 200);
    assert.equal((await recipesResponse.json()).recipes.length, 6);
    assert.match(recipesResponse.headers.get("content-security-policy"), /frame-ancestors 'none'/);
    assert.match(recipesResponse.headers.get("x-robots-tag"), /noindex/);
    assert.equal((await request("/api/plan", valid, { Origin: "https://evil.example" })).status, 403);
    const hostileHostStatus = await new Promise((resolve, reject) => {
      const req = httpRequest(base + "/api/recipes", { headers: { Host: "evil.example" } }, (res) => { res.resume(); resolve(res.statusCode); });
      req.on("error", reject); req.end();
    });
    assert.equal(hostileHostStatus, 403);
    assert.equal((await request("/api/plan", valid, { "Sec-Fetch-Site": "cross-site" })).status, 403);
    assert.equal((await request("/api/demo", {}, { "Sec-Fetch-Site": "same-site" })).status, 403);
    assert.equal((await request("/api/demo", {}, { Origin: `http://localhost:${server.address().port}` })).status, 403);
    assert.equal((await fetch(base + "/api/demo")).status, 404);
    assert.equal((await request("/api/plan", valid, { "Content-Type": "text/plain" })).status, 415);
    assert.equal((await request("/api/plan", { ...valid, task: "x".repeat(70000) })).status, 413);
    assert.equal((await request("/api/inspect", { experiment: "/tmp/does-not-exist-hill-climber-evidence" })).status, 400);
    assert.equal((await fetch(base + "/SECURITY.md")).status, 404);
    const planResponse = await request("/api/plan", valid, { Origin: base });
    assert.equal(planResponse.status, 200);
    assert.equal((await planResponse.json()).maxAttempts, 3);
    const demoResponse = await request("/api/demo", {});
    const demo = await demoResponse.json();
    assert.equal(demoResponse.status, 200, JSON.stringify(demo));
    assert.equal(demo.demo, true);
    assert.equal(demo.verified, true);
    assert.equal(demo.inspect.result.status, "promoted");
    assert.equal(demo.inspect.result.incumbent.score, 10);
    assert.equal(demo.inspect.result.applied, false);
    assert.equal(demo.candidates.length, 6);
    assert.equal(demo.candidates.filter((candidate) => candidate.status === "kept").length, 2);
    const experiment = demo.inspect.experiment;
    const receiptFile = join(experiment, "receipt.json");
    const original = readFileSync(receiptFile, "utf8");
    try {
      const changed = JSON.parse(original); changed.incumbent.score = 9999;
      writeFileSync(receiptFile, JSON.stringify(changed));
      await assert.rejects(inspectExperiment(experiment), /receipt incumbent differs/);
    } finally { writeFileSync(receiptFile, original); }
    for (const change of [(receipt) => { receipt.patch.path = "/tmp/rogue.patch"; }, (receipt) => { receipt.patch.sha256 = "0".repeat(64); }, (receipt) => { receipt.source.head = "fake-commit"; }, (receipt) => { receipt.promotion.verdict = "retained"; }]) {
      try { const altered = JSON.parse(original); change(altered); writeFileSync(receiptFile, JSON.stringify(altered)); await assert.rejects(inspectExperiment(experiment), /E_EVIDENCE/); }
      finally { writeFileSync(receiptFile, original); }
    }
    const patchPath = join(experiment, "winner.patch");
    const originalPatch = readFileSync(patchPath);
    try { writeFileSync(patchPath, "altered patch"); await assert.rejects(inspectExperiment(experiment), /winner patch differs/); }
    finally { writeFileSync(patchPath, originalPatch); }
    try {
      const altered = JSON.parse(original); altered.wall_seconds = 123456789; writeFileSync(receiptFile, JSON.stringify(altered));
      assert.notEqual((await inspectExperiment(experiment)).inspect.result.wall_seconds, 123456789);
    } finally { writeFileSync(receiptFile, original); }
    const manifestPath = join(experiment, "manifest.json");
    const manifestOriginal = readFileSync(manifestPath, "utf8");
    for (const field of ["workspace", "id", "date"]) {
      try {
        const manifest = JSON.parse(manifestOriginal); const altered = JSON.parse(original);
        if (field === "workspace") { manifest.source.workspace = "/tmp/unrelated-source"; altered.source.workspace = manifest.source.workspace; }
        if (field === "id") manifest.experiment_id = "unrelated-experiment";
        if (field === "date") manifest.created_at = "2000-01-01T00:00:00.000Z";
        const bytes = JSON.stringify(manifest); writeFileSync(manifestPath, bytes);
        altered.evidence.manifest.sha256 = createHash("sha256").update(bytes).digest("hex"); writeFileSync(receiptFile, JSON.stringify(altered));
        if (field !== "date") await assert.rejects(inspectExperiment(experiment), /manifest identity differs/);
        else assert.ok((await inspectExperiment(experiment)).inspect.result.wall_seconds < 1000);
      } finally { writeFileSync(manifestPath, manifestOriginal); writeFileSync(receiptFile, original); }
    }
    const stateFile = join(experiment, "state.json");
    const stateOriginal = readFileSync(stateFile, "utf8");
    try {
      const changed = JSON.parse(stateOriginal); changed.status = "promoted-tampered";
      writeFileSync(stateFile, JSON.stringify(changed));
      await assert.rejects(inspectExperiment(experiment), /state projection hash mismatch/);
    } finally { writeFileSync(stateFile, stateOriginal); }
    assert.equal((await inspectExperiment(experiment)).verified, true);
    const retainedRoot = mkdtempSync(join(tmpdir(), "hill-workbench-retained-"));
    try {
      const fixture = "import json,sys\nfrom pathlib import Path\nfrom tests.test_hill_climber import HillClimberTests\nr,repo,out=HillClimberTests().run_climb(Path(sys.argv[1]),'cheater',apply=False)\nprint(json.dumps({'experiment':str(out),'exit':r.returncode}))";
      const retainedRun = spawnSync("python3", ["-c", fixture, retainedRoot], { encoding: "utf8", timeout: 60000 });
      assert.equal(retainedRun.status, 0, retainedRun.stderr);
      const retained = await inspectExperiment(JSON.parse(retainedRun.stdout).experiment);
      assert.equal(retained.inspect.result.status, "retained");
      assert.equal(retained.inspect.result.incumbent.score, 0);
      assert.equal(retained.developmentBest, 100);
      assert.equal(retained.inspect.result.promotion.verdict, "reverted");
    } finally { rmSync(retainedRoot, { recursive: true, force: true }); }
  } finally { await new Promise((resolve) => server.close(resolve)); }
});
