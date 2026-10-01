import { createServer } from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, realpathSync } from "node:fs";
import { dirname, join, resolve, isAbsolute } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CLI = join(ROOT, "bin", "hill-climber");
export const recipes = JSON.parse(readFileSync(join(ROOT, "scripts", "workbench_recipes.json"), "utf8"));
export const shellQuote = (value) => `'${String(value).replaceAll("'", `'"'"'`)}'`;
const sha = (value) => createHash("sha256").update(value).digest("hex");
const stable = (value) => Array.isArray(value) ? value.map(stable) : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])])) : value;
const equal = (a, b) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));

function textField(input, key, required = false, max = 12000) {
  if (input[key] != null && typeof input[key] !== "string") throw new Error(`${key} must be text.`);
  const value = (input[key] ?? "").trim();
  if (required && !value) throw new Error(`${key} is required.`);
  if (value.length > max || /\0/.test(value)) throw new Error(`${key} is too long or contains a null character.`);
  return value;
}
function numberField(input, key, fallback, min, max, integer = true) {
  const raw = input[key];
  const value = raw === undefined || raw === "" ? fallback : Number(raw);
  if (raw === null || (raw !== undefined && !["number", "string"].includes(typeof raw)) || !Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value)))
    throw new Error(`${key} must be ${integer ? "an integer" : "a number"} between ${min} and ${max}.`);
  return value;
}
function validateEvaluatorCommands(commands) {
  const result = spawnSync("python3", ["-c", "import json,shlex,sys\ntry:\n a=[shlex.split(x) for x in json.load(sys.stdin)]\n if not all(a): raise ValueError('command is empty')\nexcept ValueError as e:\n print(str(e));sys.exit(1)"], { input: JSON.stringify(commands), encoding: "utf8", timeout: 2000, maxBuffer: 4096 });
  if (result.error || result.status !== 0) throw new Error(`Evaluator command syntax is invalid: ${result.stdout?.trim() || "Python 3 is required to check argv."}`);
}

function planWarnings(recipe, values, dev, holdout, mutable) {
  const warnings = ["Review evaluator commands before running: they execute with your local authority.", "Commit source changes before running; keep private holdout code and data outside the repository.", "This command proposes a patch without applying it. It uses your Codex capacity when you run it."];
  if (dev === holdout) warnings.push("Development and holdout commands are identical. This cannot prove generalization; use genuinely unseen cases.");
  if (mutable.includes("**/*") || mutable.includes("*")) warnings.push("The mutable surface is broad. Narrow it to the files needed for this objective.");
  if (recipe.id !== "code" && (values.repeats < 3 || values["holdout-repeats"] < 3)) warnings.push("This task can have noisy scores. Use at least 3 repeats and set minimum gain above the measured noise floor.");
  if (recipe.id !== "code" && values["min-gain"] === 0) warnings.push("Measure baseline noise and set a meaningful minimum gain before interpreting small improvements.");
  if (values["evaluation-parallel"] > 1) warnings.push("Only overlap independent graders. Keep timing, shared resources and rate-limited evaluators serial.");
  return warnings;
}

function planPaths(input) {
  const workspace = textField(input, "workspace", true, 4096);
  const out = textField(input, "out", true, 4096);
  if (!isAbsolute(workspace) || !isAbsolute(out)) throw new Error("Use absolute repository and experiment paths.");
  if (resolve(out) === resolve(workspace) || resolve(out).startsWith(`${resolve(workspace)}/`)) throw new Error("Put experiment evidence outside the source repository.");
  return { workspace, out };
}

export function buildPlan(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Provide an experiment object.");
  const recipe = recipes.find((item) => item.id === input.recipe);
  if (!recipe) throw new Error("Choose a task type.");
  const { workspace, out } = planPaths(input);
  const task = textField(input, "task", true, 4000);
  const dev = textField(input, "eval", true, 4096);
  const holdout = textField(input, "holdoutEval", true, 4096);
  validateEvaluatorCommands([dev, holdout]);
  const mutable = textField(input, "mutable", true, 4096).split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  if (mutable.length > 20 || mutable.some((item) => isAbsolute(item) || item.split("/").includes("..") || item.startsWith("!"))) throw new Error("Use at most 20 positive repository-relative mutable globs.");
  const details = textField(input, "details") || recipe.details;
  const model = textField(input, "model", false, 160) || "gpt-6.1-sol";
  const reasoning = textField(input, "reasoning", false, 20) || "high";
  if (!["minimal", "low", "medium", "high", "xhigh", "max", "ultra"].includes(reasoning)) throw new Error("Choose a supported reasoning effort.");
  const options = [
    ["candidates", "candidates", 3, 1, 20], ["rounds", "rounds", 1, 1, 100],
    ["repeats", "repeats", recipe.repeats, 1, 10], ["holdoutRepeats", "holdout-repeats", recipe.holdoutRepeats, 1, 10],
    ["minGain", "min-gain", recipe.minGain, 0, 1e12, false],
    ["maxWallSeconds", "max-wall-seconds", 1800, 1, 604800], ["maxTokens", "max-tokens", 150000, 1, 100000000],
    ["generationParallel", "generation-parallel", 2, 1, 8], ["evaluationParallel", "evaluation-parallel", 1, 1, 8],
  ].map(([key, flag, fallback, min, max, integer]) => [flag, numberField(input, key, fallback, min, max, integer)]);
  const values = Object.fromEntries(options);
  const warnings = planWarnings(recipe, values, dev, holdout, mutable);
  const brief = `# Improvement brief\n\n## Objective\n${task}\n\n## Task family\n${recipe.name}\n\n## Constraints and context\n${details}\n\n## Evaluation design (adapt before use)\nScore: ${recipe.score}\nGates: ${recipe.gates}\nFeedback: ${recipe.feedback}\n\n## Editable surface\n${mutable.map((item) => `- ${item}`).join("\n")}\n\n## Acceptance\nA strict development gain, passing protected gates and a one-time unseen holdout gain. Review the verified receipt and patch. A retained or blocked run leaves the baseline intact.\n`;
  // Equals-form values are both shell-safe and argparse-safe when free text
  // begins with a dash (for example an objective literally named --help).
  const args = ["python3", CLI, "run", ...[["workspace", workspace], ["task", task], ["details", details], ["eval", dev], ["holdout-eval", holdout], ...mutable.map((item) => ["mutable", item]), ...options, ["candidate-timeout", 600], ["eval-timeout", 120], ["max-failures", 2], ["model", model], ["reasoning", reasoning], ["out", out]].map(([flag, value]) => `--${flag}=${value}`), "--no-apply"];
  return { command: args.map(shellQuote).join(" "), brief, warnings, maxAttempts: values.candidates * values.rounds };
}

export function runProgram(command, args, { env = process.env, timeout = 30000 } = {}) {
  return new Promise((res, rej) => {
    const child = spawn(command, args, { env, detached: process.platform !== "win32", stdio: ["ignore", "pipe", "pipe"] });
    const chunks = []; let size = 0; let failure = null;
    const stop = () => { try { if (process.platform !== "win32" && child.pid) process.kill(-child.pid, "SIGKILL"); else child.kill("SIGKILL"); } catch { child.kill("SIGKILL"); } };
    const timer = setTimeout(() => { failure = new Error("Evidence inspection timed out."); stop(); }, timeout);
    child.stdout.on("data", (chunk) => { if (failure) return; size += chunk.length; if (size > 16 * 1024 * 1024) { failure = new Error("Evidence is too large for the workbench."); stop(); } else chunks.push(chunk); });
    child.stderr.resume();
    child.on("error", (error) => { failure = error; });
    child.on("close", (code) => { clearTimeout(timer); if (failure) { stop(); rej(failure); } else res({ code, stdout: Buffer.concat(chunks).toString("utf8") }); });
  });
}

export async function inspectExperiment(experiment) {
  if (typeof experiment !== "string" || !isAbsolute(experiment) || experiment.length > 4096 || experiment.includes("\0")) throw new Error("Use an absolute experiment directory.");
  const result = await runProgram("python3", [CLI, "inspect", experiment, "--json", "--quiet"]);
  let inspection;
  try { inspection = JSON.parse(result.stdout); } catch { throw new Error("Controller did not return valid evidence."); }
  if (result.code !== 0 || !inspection.ok) throw new Error(`${inspection.error?.code ?? "E_INSPECT"}: ${inspection.error?.message ?? "Evidence verification failed."}`);
  const ledger = readFileSync(join(experiment, "events.jsonl"), "utf8");
  if (Buffer.byteLength(ledger) > 16 * 1024 * 1024) throw new Error("Evidence is too large for the workbench.");
  const records = ledger.trim().split("\n").filter(Boolean).map((line) => JSON.parse(line));
  let previous = null;
  for (const [index, record] of records.entries()) {
    const material = { ...record }; delete material.hash;
    if (record.seq !== index + 1 || record.prev_hash !== previous || record.hash !== sha(`${JSON.stringify(stable(material))}\n`)) throw new Error("E_EVIDENCE: ledger changed during inspection. Refresh its checkpoint.");
    previous = record.hash;
  }
  // Match the file read here to the tail just verified by the controller;
  // fail safely if the running experiment changed in between the reads.
  if (records.at(-1)?.hash !== inspection.status.ledger_hash || records.length !== inspection.status.ledger_seq) throw new Error("Experiment changed during inspection. Refresh to read its latest checkpoint.");
  const manifestBytes = readFileSync(join(experiment, "manifest.json"));
  const receipt = inspection.result;
  const manifest = JSON.parse(manifestBytes);
  const created = records.find((record) => record.type === "experiment_created");
  const source = { workspace: manifest.config.workspace, head: created?.payload.source_head };
  if (!equal(source, manifest.source) || manifest.experiment_id !== created?.payload.experiment_id) throw new Error("E_EVIDENCE: manifest identity differs from the ledger.");
  if (receipt) {
    for (const key of ["baseline", "incumbent", "counts", "usage", "applied", "status", "terminal_reason"]) {
      if (!equal(receipt[key], inspection.status[key])) throw new Error(`E_EVIDENCE: receipt ${key} differs from verified state.`);
    }
    const promotionEvent = records.filter((record) => ["holdout_completed", "holdout_abandoned", "promotion_skipped"].includes(record.type)).at(-1);
    const promotion = promotionEvent?.type === "promotion_skipped" ? { verdict: "retained", holdout_used: false } : promotionEvent?.payload;
    if (!promotion || !equal(promotion, receipt.promotion)) throw new Error("E_EVIDENCE: receipt promotion differs from the ledger.");
    if (receipt.evidence?.ledger?.sha256 !== sha(ledger) || receipt.evidence?.manifest?.sha256 !== sha(manifestBytes)) throw new Error("E_EVIDENCE: receipt evidence hashes differ.");
    if (receipt.task !== manifest.config.task) throw new Error("E_EVIDENCE: receipt objective differs from the manifest.");
    if (!equal(receipt.source, manifest.source)) throw new Error("E_EVIDENCE: receipt source differs from the manifest.");
    const patchEvent = records.filter((record) => record.type === "winner_patch_prepared").at(-1)?.payload;
    let patch = null;
    if (patchEvent) {
      const patchPath = join(realpathSync(experiment), "winner.patch");
      let claimedPath = null;
      try { claimedPath = realpathSync(receipt.patch?.path); } catch {}
      if (patchEvent.patch !== "winner.patch" || !receipt.patch || claimedPath !== realpathSync(patchPath) || receipt.patch.sha256 !== patchEvent.patch_sha256 || sha(readFileSync(patchPath)) !== patchEvent.patch_sha256) throw new Error("E_EVIDENCE: winner patch differs from the ledger.");
      patch = { path: patchPath, sha256: patchEvent.patch_sha256 };
    } else if (receipt.patch !== null) throw new Error("E_EVIDENCE: receipt patch has no ledger record.");
    // Publish only fields anchored in verified state/manifest/ledger. Receipt
    // display timestamps and report metadata are not controller-committed.
    inspection.result = { ...Object.fromEntries(["baseline", "incumbent", "counts", "usage", "applied", "status", "terminal_reason"].map((key) => [key, inspection.status[key]])), task: manifest.config.task, source, promotion, patch, experiment_id: created.payload.experiment_id, rounds_completed: inspection.status.round, wall_seconds: Math.max(0, (Date.parse(records.at(-1).at) - Date.parse(created.at)) / 1000), evidence: { ledger: { path: join(experiment, "events.jsonl"), sha256: sha(ledger) }, manifest: { path: join(experiment, "manifest.json"), sha256: sha(manifestBytes) } } };
  }
  const candidates = new Map();
  for (const { type, payload } of records) {
    if (!payload.candidate_id || !/^r\d+-c\d+$/.test(payload.candidate_id)) continue;
    const item = candidates.get(payload.candidate_id) ?? { id: payload.candidate_id, round: payload.round, parent: payload.parent, score: null, gates: null, status: "started", verdict: "started", reason: null, feedback: [] };
    if (payload.metadata) { item.mechanism = payload.metadata.mechanism; item.hypothesis = payload.metadata.hypothesis; }
    if (type === "candidate_evaluated") { item.score = payload.evaluation.score; item.gates = payload.evaluation.gates_passed; item.feedback = payload.evaluation.feedback; item.status = "evaluated"; }
    if (["candidate_kept", "candidate_rejected", "candidate_invalid", "candidate_crashed"].includes(type)) { item.status = type.replace("candidate_", ""); item.reason = payload.reason ?? payload.code ?? null; }
    item.verdict = item.status;
    candidates.set(item.id, item);
  }
  const developmentBest = records.filter((record) => record.type === "round_selected").at(-1)?.payload.incumbent_score_after ?? inspection.status.baseline?.score ?? null;
  return { inspect: inspection, candidates: [...candidates.values()].sort((a, b) => a.id.localeCompare(b.id)), developmentBest, verified: true, demo: false, warnings: [] };
}

let demoPromise;
async function demo() {
  if (!demoPromise) demoPromise = (async () => {
    const root = mkdtempSync(join(tmpdir(), "hill-climber-workbench-demo-"));
    const repo = join(root, "source"); const bin = join(root, "bin");
    mkdirSync(repo); mkdirSync(bin);
    writeFileSync(join(repo, "solution.txt"), "0\n");
    writeFileSync(join(bin, "codex"), '#!/bin/sh\nprintf "Logged in using ChatGPT\\n"\n', { mode: 0o755 });
    for (const args of [["init", "-q", repo], ["-C", repo, "config", "user.name", "Hill Climber Demo"], ["-C", repo, "config", "user.email", "demo@localhost"], ["-C", repo, "add", "solution.txt"], ["-C", repo, "commit", "-qm", "baseline"]]) {
      const response = await runProgram("git", args); if (response.code !== 0) throw new Error("Cannot prepare the deterministic demo.");
    }
    const experiment = join(root, "experiment");
    const response = await runProgram("python3", [CLI, "run", "--workspace", repo, "--task", "Deterministic demo: improve a bounded integer score", "--eval", `python3 ${shellQuote(join(ROOT, "tests", "fixtures", "evaluate_climb_fixture.py"))} staircase development`, "--holdout-eval", `python3 ${shellQuote(join(ROOT, "tests", "fixtures", "evaluate_climb_fixture.py"))} staircase holdout`, "--mutable", "solution.txt", "--candidates", "3", "--rounds", "2", "--out", experiment, "--no-apply", "--json", "--quiet"], { timeout: 90000, env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, HILL_CLIMBER_CODEX_MODULE: join(ROOT, "tests", "fixtures", "fake_codex_sdk.mjs"), HILL_CLIMBER_FAKE_SCENARIO: "staircase" } });
    if (response.code !== 0) throw new Error("Deterministic demo failed. Check Python, Git and installed Node dependencies.");
    return { ...(await inspectExperiment(experiment)), demo: true };
  })().catch((error) => { demoPromise = null; throw error; });
  return demoPromise;
}

export function createWorkbenchServer() {
  let activeInspections = 0;
  return createServer(async (req, res) => {
    const address = req.socket.localAddress;
    const hosts = [`127.0.0.1:${req.socket.localPort}`, `localhost:${req.socket.localPort}`];
    const host = req.headers.host;
    const origin = req.headers.origin;
    const validOrigin = !origin || origin === `http://${host}`;
    res.setHeader("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
    res.setHeader("X-Content-Type-Options", "nosniff"); res.setHeader("Referrer-Policy", "no-referrer"); res.setHeader("Cache-Control", "no-store"); res.setHeader("X-Robots-Tag", "noindex, nofollow");
    const send = (status, value) => { res.writeHead(status, { "Content-Type": "application/json" }); res.end(JSON.stringify(value)); };
    if (address !== "127.0.0.1" || !hosts.includes(host) || !validOrigin || ["cross-site", "same-site"].includes(req.headers["sec-fetch-site"])) return send(403, { error: "Local same-origin access only." });
    let route;
    try { route = new URL(req.url, `http://${host}`).pathname; } catch { return send(400, { error: "Invalid URL." }); }
    try {
      if (req.method === "GET" && route === "/api/recipes") return send(200, { recipes });
      if (req.method === "POST" && ["/api/plan", "/api/inspect", "/api/demo"].includes(route)) {
        if (req.headers["content-type"]?.split(";")[0] !== "application/json") return send(415, { error: "Send application/json." });
        const chunks = []; let size = 0;
        for await (const chunk of req) { size += chunk.length; if (size > 65536) return send(413, { error: "Request is too large." }); chunks.push(chunk); }
        let body; try { body = JSON.parse(Buffer.concat(chunks)); } catch { return send(400, { error: "Invalid JSON." }); }
        if (route === "/api/plan") return send(200, buildPlan(body));
        if (route === "/api/demo") return send(200, await demo());
        if (activeInspections >= 2) return send(429, { error: "Two inspections are already running. Try again shortly." });
        activeInspections += 1;
        try { return send(200, await inspectExperiment(body?.experiment)); } finally { activeInspections -= 1; }
      }
      const assets = { "/": ["index.html", "text/html; charset=utf-8"], "/app.js": ["app.js", "text/javascript; charset=utf-8"], "/styles.css": ["styles.css", "text/css; charset=utf-8"] };
      if (req.method !== "GET" || !assets[route]) return send(404, { error: "Not found." });
      const [file, contentType] = assets[route];
      res.writeHead(200, { "Content-Type": contentType }); res.end(readFileSync(join(ROOT, "web", file)));
    } catch (error) { send(400, { error: error.message }); }
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.argv[2] ?? 4388);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Port must be between 1 and 65535.");
  const server = createWorkbenchServer();
  server.on("error", (error) => { console.error(`Cannot start workbench: ${error.message}`); process.exitCode = 1; });
  server.listen(port, "127.0.0.1", () => console.log(`Hill Climber workbench: http://127.0.0.1:${port}\nKeep this terminal open. Preparing a plan makes no model calls.`));
}
