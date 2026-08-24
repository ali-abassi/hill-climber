#!/usr/bin/env node

/**
 * Codex-SDK candidate generator for a bounded, evidence-gated repository hill climb.
 *
 * The model only edits isolated candidate worktrees. This controller owns the
 * baseline, detached evaluation, selection, budgets, holdout, application,
 * append-only evidence, and recovery boundary.
 */

import { spawn, spawnSync } from "node:child_process";
import {
  closeSync,
  constants as fsConstants,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
  writeSync,
} from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { minimatch } from "minimatch";

const SCHEMA = "hill-climber.v1";
const MAX_CAPTURE_BYTES = 2 * 1024 * 1024;
// Candidate agents commonly run Python checks. Bytecode is execution debris,
// not an authored repository change, so prevent it instead of weakening the
// mutable-path boundary or silently deleting candidate output.
process.env.PYTHONDONTWRITEBYTECODE ??= "1";
const STRATEGIES = [
  ["root-cause", "Diagnose the broadest recurring failure class and fix one root cause."],
  ["edge-coverage", "Improve one correctness mechanism that covers edge cases without case-specific hacks."],
  ["simplify", "Replace one brittle or duplicated mechanism with a smaller, clearer one."],
  ["alternative", "Try one materially different implementation mechanism suggested by the evidence."],
  ["adversarial", "Harden one mechanism against malformed, boundary, or adversarial inputs."],
];

class ClimbError extends Error {
  constructor(code, message, exitCode = 2, details = {}) {
    super(message);
    this.name = "ClimbError";
    this.code = code;
    this.exitCode = exitCode;
    this.details = details;
  }
}

class InterruptedError extends ClimbError {
  constructor(message = "interrupted") {
    super("E_INTERRUPTED", message, 130);
    this.name = "InterruptedError";
  }
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}

function jsonBytes(value) {
  return `${JSON.stringify(stable(value))}\n`;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function fileSha256(path) {
  return sha256(readFileSync(path));
}

function atomicWrite(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  const fd = openSync(temporary, fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY, 0o600);
  try {
    const bytes = Buffer.from(typeof value === "string" ? value : jsonBytes(value));
    writeSync(fd, bytes);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(temporary, path);
  try {
    const dirFd = openSync(dirname(path), fsConstants.O_RDONLY);
    try { fsyncSync(dirFd); } finally { closeSync(dirFd); }
  } catch {
    // Directory fsync is unavailable on some platforms; the file is still fsynced.
  }
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new ClimbError("E_EVIDENCE", `cannot read JSON evidence ${path}: ${error.message}`, 3);
  }
}

function bounded(value, limit = 4000) {
  const text = String(value ?? "").replace(/\0/g, "");
  return text.length <= limit ? text : `${text.slice(0, limit)}\n...[truncated]`;
}

function safeLine(value) {
  return String(value ?? "")
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function xml(value) {
  return safeLine(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function shortLine(value, limit = 80) {
  const line = safeLine(value);
  return line.length <= limit ? line : `${line.slice(0, Math.max(0, limit - 1))}…`;
}

function scoreText(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(3).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1") : "—";
}

function normalizePath(path) {
  return path.split(sep).join("/").replace(/^\.\//, "");
}

function now() {
  return new Date().toISOString();
}

function monotonicSeconds(started) {
  return Number((Number(process.hrtime.bigint() - started) / 1e9).toFixed(3));
}

function progress(config, label, message) {
  if (config.quiet) return;
  process.stderr.write(`${safeLine(label)} ${safeLine(message)}\n`);
}

function ensureInside(root, path, label) {
  const base = resolve(root);
  const target = resolve(path);
  if (target !== base && !target.startsWith(`${base}${sep}`)) {
    throw new ClimbError("E_PATH", `${label} must stay inside ${base}: ${target}`);
  }
  return target;
}

function normalizeEnvKeys(value) {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) {
    throw new ClimbError("E_USAGE", "env_keys must be an array of variable names");
  }
  const keys = [];
  for (const key of value) {
    if (typeof key !== "string" || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      throw new ClimbError("E_USAGE", `invalid environment variable name: ${key}`);
    }
    if (key.startsWith("HILL_CLIMBER_")) {
      throw new ClimbError("E_USAGE", `cannot override reserved environment variable: ${key}`);
    }
    keys.push(key);
  }
  return [...new Set(keys)].sort();
}

function requestedEnv(keys) {
  const result = {};
  const missing = [];
  for (const key of keys ?? []) {
    if (process.env[key] === undefined) missing.push(key);
    else result[key] = process.env[key];
  }
  if (missing.length) {
    throw new ClimbError("E_ENV",
      `required evaluator environment variable(s) are missing: ${missing.join(", ")}`, 2,
      { next_action: `export ${missing.join(" ")} and rerun or resume with --env KEY` });
  }
  return result;
}

function sanitizeEnv(extra = {}) {
  const allowed = [
    "HOME", "PATH", "SHELL", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR",
    "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
    "CODEX_HOME", "CODEX_CA_CERTIFICATE", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
  ];
  const result = {};
  for (const key of allowed) if (process.env[key] !== undefined) result[key] = process.env[key];
  return { ...result, ...extra };
}

function runSync(argv, options = {}) {
  const result = spawnSync(argv[0], argv.slice(1), {
    cwd: options.cwd,
    env: options.env ?? sanitizeEnv(),
    encoding: "utf8",
    maxBuffer: MAX_CAPTURE_BYTES,
    input: options.input,
  });
  if (result.error) {
    throw new ClimbError("E_PROCESS", `cannot start ${argv[0]}: ${result.error.message}`);
  }
  if (!options.allowFailure && result.status !== 0) {
    const detail = bounded(result.stderr || result.stdout || `exit ${result.status}`, 1200).trim();
    throw new ClimbError("E_PROCESS", `${argv.join(" ")} failed: ${detail}`);
  }
  return result;
}

async function runProcess(argv, options = {}) {
  const timeoutMs = Math.max(1, Number(options.timeoutSeconds ?? 300) * 1000);
  if (options.signal?.aborted) throw new InterruptedError(String(options.signal.reason ?? "interrupted"));
  return await new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(argv[0], argv.slice(1), {
      cwd: options.cwd,
      env: options.env ?? sanitizeEnv(),
      stdio: ["ignore", "pipe", "pipe"],
      detached: process.platform !== "win32",
    });
    let stdout = Buffer.alloc(0);
    let stderr = Buffer.alloc(0);
    let settled = false;
    let pendingError = null;
    const finish = (error, result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", abort);
      if (error) rejectPromise(error); else resolvePromise(result);
    };
    const stop = (signal = "SIGKILL") => {
      try {
        if (process.platform !== "win32" && child.pid) process.kill(-child.pid, signal);
        else child.kill(signal);
      } catch { child.kill(signal); }
    };
    const abort = () => {
      stop("SIGTERM");
      setTimeout(() => stop("SIGKILL"), 1000).unref();
    };
    options.signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(() => {
      pendingError = new ClimbError("E_TIMEOUT", `${argv[0]} timed out after ${timeoutMs / 1000}s`);
      abort();
    }, timeoutMs);
    timer.unref();
    const collect = (current, chunk) => {
      const next = Buffer.concat([current, chunk]);
      if (next.length > MAX_CAPTURE_BYTES) {
        pendingError ??= new ClimbError("E_OUTPUT_LIMIT", `${argv[0]} output exceeded ${MAX_CAPTURE_BYTES} bytes`);
        abort();
        return current;
      }
      return next;
    };
    child.stdout.on("data", (chunk) => { stdout = collect(stdout, chunk); });
    child.stderr.on("data", (chunk) => { stderr = collect(stderr, chunk); });
    child.on("error", (error) => finish(new ClimbError("E_PROCESS", `cannot start ${argv[0]}: ${error.message}`)));
    child.on("close", (code, signal) => {
      if (options.signal?.aborted) return finish(new InterruptedError(String(options.signal.reason ?? "interrupted")));
      if (pendingError) return finish(pendingError);
      finish(null, { code: code ?? 1, signal, stdout: stdout.toString("utf8"), stderr: stderr.toString("utf8") });
    });
  });
}

class Ledger {
  constructor(path) {
    this.path = path;
    this.records = this.verify();
  }

  verify() {
    if (!existsSync(this.path)) return [];
    const lines = readFileSync(this.path, "utf8").split("\n").filter(Boolean);
    const records = [];
    let previous = null;
    for (let index = 0; index < lines.length; index += 1) {
      let record;
      try { record = JSON.parse(lines[index]); }
      catch (error) { throw new ClimbError("E_EVIDENCE", `ledger line ${index + 1} is invalid: ${error.message}`, 3); }
      const claimed = record.hash;
      const material = { ...record };
      delete material.hash;
      const actual = sha256(jsonBytes(material));
      if (record.seq !== index + 1 || record.prev_hash !== previous || claimed !== actual) {
        throw new ClimbError("E_EVIDENCE", `ledger chain mismatch at line ${index + 1}`, 3);
      }
      previous = claimed;
      records.push(record);
    }
    return records;
  }

  append(type, payload = {}) {
    const material = {
      schema: `${SCHEMA}.event`,
      seq: this.records.length + 1,
      at: now(),
      type,
      payload,
      prev_hash: this.records.at(-1)?.hash ?? null,
    };
    const record = { ...material, hash: sha256(jsonBytes(material)) };
    mkdirSync(dirname(this.path), { recursive: true });
    const fd = openSync(this.path, fsConstants.O_CREAT | fsConstants.O_APPEND | fsConstants.O_WRONLY, 0o600);
    try {
      writeSync(fd, Buffer.from(jsonBytes(record)));
      fsyncSync(fd);
    } finally { closeSync(fd); }
    this.records.push(record);
    return record;
  }
}

class RunLock {
  constructor(path) { this.path = path; this.fd = null; }
  acquire() {
    mkdirSync(dirname(this.path), { recursive: true });
    try {
      this.fd = openSync(this.path, fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY, 0o600);
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      const owner = readJson(this.path);
      let live = false;
      try { process.kill(owner.pid, 0); live = true; } catch {}
      if (live) throw new ClimbError("E_BUSY", `experiment is owned by process ${owner.pid}`, 4);
      unlinkSync(this.path);
      this.fd = openSync(this.path, fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY, 0o600);
    }
    writeSync(this.fd, Buffer.from(jsonBytes({ pid: process.pid, started_at: now() })));
    fsyncSync(this.fd);
  }
  release() {
    if (this.fd !== null) closeSync(this.fd);
    this.fd = null;
    try { unlinkSync(this.path); } catch {}
  }
}

function usageTotal(usage) {
  if (!usage) return 0;
  return Number(usage.input_tokens ?? 0) + Number(usage.output_tokens ?? 0);
}

function usageZero() {
  return {
    input_tokens: 0, cached_input_tokens: 0, cache_write_input_tokens: 0,
    output_tokens: 0, reasoning_output_tokens: 0,
  };
}

function addUsage(target, usage) {
  if (!usage) return target;
  for (const key of Object.keys(target)) target[key] += Number(usage[key] ?? 0);
  return target;
}

function anySignal(signals) {
  if (typeof AbortSignal.any === "function") return AbortSignal.any(signals);
  const controller = new AbortController();
  const abort = (signal) => {
    if (!controller.signal.aborted) controller.abort(signal.reason);
  };
  for (const signal of signals) {
    if (signal.aborted) abort(signal);
    else signal.addEventListener("abort", () => abort(signal), { once: true });
  }
  return controller.signal;
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function evaluatorResult(raw, label) {
  let parsed;
  try { parsed = JSON.parse(raw.trim()); }
  catch (error) { throw new ClimbError("E_EVALUATOR_OUTPUT", `${label} did not emit one JSON object: ${error.message}`); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || !Number.isFinite(parsed.score)) {
    throw new ClimbError("E_EVALUATOR_OUTPUT", `${label} requires a finite numeric score`);
  }
  const gates = parsed.gates ?? {};
  if (!gates || typeof gates !== "object" || Array.isArray(gates) ||
      Object.values(gates).some((value) => typeof value !== "boolean")) {
    throw new ClimbError("E_EVALUATOR_OUTPUT", `${label} gates must be a string-to-boolean object`);
  }
  const rawFeedback = parsed.feedback ?? [];
  const feedback = typeof rawFeedback === "string" ? [rawFeedback] : rawFeedback;
  if (!Array.isArray(feedback) || feedback.some((value) => typeof value !== "string")) {
    throw new ClimbError("E_EVALUATOR_OUTPUT", `${label} feedback must be a string or array of strings`);
  }
  return {
    score: Number(parsed.score),
    gates,
    details: bounded(parsed.details ?? "", 12000),
    metrics: parsed.metrics ?? {},
    feedback: feedback.map((value) => bounded(value, 2000).trim()).filter(Boolean).slice(0, 20),
  };
}

function allGatesPass(gates) {
  return Object.values(gates).every(Boolean);
}

function pathAllowed(path, mutable) {
  const normalized = normalizePath(path);
  return mutable.some((pattern) => minimatch(normalized, pattern, { dot: true, matchBase: false }));
}

function readStdin() {
  return new Promise((resolvePromise, rejectPromise) => {
    let input = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { input += chunk; });
    process.stdin.on("end", () => {
      try { resolvePromise(JSON.parse(input)); }
      catch (error) { rejectPromise(new ClimbError("E_USAGE", `invalid controller input: ${error.message}`)); }
    });
    process.stdin.on("error", rejectPromise);
  });
}

function validateConfig(config) {
  if (config.schema !== `${SCHEMA}.request`) throw new ClimbError("E_USAGE", "unsupported climb request schema");
  if (!["run", "resume", "status", "inspect", "stop"].includes(config.action)) {
    throw new ClimbError("E_USAGE", `unknown climb action: ${config.action}`);
  }
  if (config.action === "run") {
    for (const key of ["workspace", "task", "eval_argv", "holdout_argv", "mutable", "out"]) {
      if (config[key] === undefined || config[key] === null || config[key] === "") {
        throw new ClimbError("E_USAGE", `missing required climb field: ${key}`);
      }
    }
    if (!Array.isArray(config.eval_argv) || !config.eval_argv.length ||
        !Array.isArray(config.holdout_argv) || !config.holdout_argv.length) {
      throw new ClimbError("E_USAGE", "evaluation commands must be non-empty argv arrays");
    }
    if (!Array.isArray(config.mutable) || !config.mutable.length) {
      throw new ClimbError("E_USAGE", "at least one mutable glob is required");
    }
    normalizeEnvKeys(config.env_keys);
  } else if (!config.experiment) {
    throw new ClimbError("E_USAGE", `hill-climber ${config.action} requires an experiment path`);
  }
}

function git(cwd, args, options = {}) {
  return runSync(["git", ...args], { cwd, ...options });
}

function gitText(cwd, args) {
  return git(cwd, args).stdout.trim();
}

function assertCleanRepository(workspace) {
  const root = gitText(workspace, ["rev-parse", "--show-toplevel"]);
  if (resolve(root) !== resolve(workspace)) {
    throw new ClimbError("E_WORKSPACE", `--workspace must be the Git repository root: ${root}`);
  }
  if (gitText(workspace, ["status", "--porcelain=v1", "--untracked-files=normal"])) {
    throw new ClimbError("E_DIRTY", "source repository must be clean before a climb", 2,
      { next_action: "commit, stash, or remove local changes, then rerun" });
  }
  return { root, head: gitText(workspace, ["rev-parse", "HEAD"]) };
}

function safeRemoveWorktree(repo, path) {
  if (!existsSync(path)) return;
  runSync(["git", "-C", repo, "worktree", "remove", "--force", path], { allowFailure: true });
  if (existsSync(path)) rmSync(path, { recursive: true, force: true });
  runSync(["git", "-C", repo, "worktree", "prune"], { allowFailure: true });
}

function addWorktree(repo, path, commit) {
  safeRemoveWorktree(repo, path);
  mkdirSync(dirname(path), { recursive: true });
  runSync(["git", "-C", repo, "worktree", "add", "--detach", path, commit]);
}

function changedPaths(worktree) {
  const result = git(worktree, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]);
  const entries = result.stdout.split("\0").filter(Boolean);
  const paths = [];
  for (const entry of entries) {
    const body = entry.slice(3);
    const renamed = body.includes(" -> ") ? body.split(" -> ").at(-1) : body;
    paths.push(normalizePath(renamed));
  }
  return [...new Set(paths)].sort();
}

function removeExecutionDebris(worktree) {
  const removed = [];
  for (const path of changedPaths(worktree)) {
    const parts = path.split("/");
    const pythonBytecode = parts.includes("__pycache__") && /\.(?:pyc|pyo)$/.test(path);
    const pytestCache = parts.includes(".pytest_cache");
    const coverageData = parts.at(-1) === ".coverage";
    if (!pythonBytecode && !pytestCache && !coverageData) continue;
    rmSync(ensureInside(worktree, join(worktree, path), "execution debris"), { recursive: true, force: true });
    removed.push(path);
  }
  return removed;
}

function candidateComplexity(repo, baseline, commit) {
  const output = gitText(repo, ["diff", "--numstat", baseline, commit]);
  let lines = 0;
  let files = 0;
  for (const row of output.split("\n").filter(Boolean)) {
    const [added, deleted] = row.split("\t");
    lines += (Number(added) || 0) + (Number(deleted) || 0);
    files += 1;
  }
  return { files, lines };
}

function applyRef(repo, name, commit) {
  git(repo, ["update-ref", `refs/hill-climber/${name}`, commit]);
}

function candidateCommit(worktree, candidateId) {
  git(worktree, ["add", "-A"]);
  git(worktree, ["diff", "--cached", "--check"]);
  const result = git(worktree, [
    "-c", "user.name=hill-climber", "-c", "user.email=hill-climber@localhost",
    "commit", "--no-gpg-sign", "-m", `hill-climber candidate ${candidateId}`,
  ], { allowFailure: true });
  if (result.status !== 0) {
    throw new ClimbError("E_NO_CHANGE", `candidate ${candidateId} produced no committable change`);
  }
  return gitText(worktree, ["rev-parse", "HEAD"]);
}

function manifestPath(experiment) { return join(experiment, "manifest.json"); }
function statePath(experiment) { return join(experiment, "state.json"); }
function ledgerPath(experiment) { return join(experiment, "events.jsonl"); }

function saveState(context) {
  const last = context.ledger.records.at(-1) ?? null;
  context.state.ledger_seq = last?.seq ?? 0;
  context.state.ledger_hash = last?.hash ?? null;
  context.state.updated_at = now();
  delete context.state.state_hash;
  context.state.state_hash = sha256(jsonBytes(context.state));
  atomicWrite(statePath(context.experiment), context.state);
}

function append(context, type, payload = {}) {
  const record = context.ledger.append(type, payload);
  saveState(context);
  return record;
}

function loadContext(experiment, request = {}) {
  const root = resolve(experiment);
  const manifest = readJson(manifestPath(root));
  if (manifest.schema !== `${SCHEMA}.manifest`) throw new ClimbError("E_EVIDENCE", "unsupported climb manifest", 3);
  const ledger = new Ledger(ledgerPath(root));
  const state = readJson(statePath(root));
  const claimedStateHash = state.state_hash;
  const stateMaterial = { ...state };
  delete stateMaterial.state_hash;
  if (claimedStateHash !== sha256(jsonBytes(stateMaterial))) {
    throw new ClimbError("E_EVIDENCE", "state projection hash mismatch", 3);
  }
  const last = ledger.records.at(-1) ?? null;
  if (state.ledger_seq !== (last?.seq ?? 0) || state.ledger_hash !== (last?.hash ?? null)) {
    throw new ClimbError("E_EVIDENCE", "state does not match the committed ledger tail", 3);
  }
  const created = ledger.records.find((record) => record.type === "experiment_created");
  if (!created || created.payload.source_head !== manifest.source?.head ||
      created.payload.config_sha256 !== sha256(jsonBytes(manifest.config))) {
    throw new ClimbError("E_EVIDENCE", "manifest does not match the committed experiment identity", 3);
  }
  const persistedConfig = { ...manifest.config };
  // Legacy manifests (before env values were removed from durable state) may
  // contain `extra_env`. Use only its names at runtime; never re-emit values.
  const legacyEnvKeys = persistedConfig.extra_env && typeof persistedConfig.extra_env === "object"
    ? Object.keys(persistedConfig.extra_env) : [];
  delete persistedConfig.extra_env;
  const envKeys = normalizeEnvKeys(persistedConfig.extra_env_keys ?? legacyEnvKeys);
  return {
    experiment: root,
    manifest,
    ledger,
    state,
    config: { ...persistedConfig, extra_env_keys: envKeys,
      quiet: Boolean(request.quiet), json: Boolean(request.json) },
    repo: join(root, "repo"),
    abortController: new AbortController(),
  };
}

function createContext(request) {
  const workspace = resolve(request.workspace);
  const out = resolve(request.out);
  if (existsSync(out)) throw new ClimbError("E_EXISTS", `experiment already exists: ${out}`);
  const source = assertCleanRepository(workspace);
  mkdirSync(dirname(out), { recursive: true, mode: 0o700 });
  mkdirSync(out, { recursive: false, mode: 0o700 });
  const repo = join(out, "repo");
  runSync(["git", "clone", "--local", "--no-hardlinks", "--no-tags", workspace, repo]);
  const cloneHead = gitText(repo, ["rev-parse", "HEAD"]);
  if (cloneHead !== source.head) throw new ClimbError("E_DRIFT", "internal clone does not match source HEAD", 3);
  applyRef(repo, "baseline", source.head);
  applyRef(repo, "incumbent", source.head);
  const config = {
    workspace,
    task: String(request.task).trim(),
    details: String(request.details ?? "").trim(),
    eval_argv: request.eval_argv,
    holdout_argv: request.holdout_argv,
    holdout_independent: JSON.stringify(request.eval_argv) !== JSON.stringify(request.holdout_argv),
    setup_argv: request.setup_argv ?? [],
    extra_env_keys: normalizeEnvKeys(request.env_keys),
    mutable: request.mutable.map(normalizePath),
    candidates: request.candidates,
    rounds: request.rounds,
    generation_parallel: request.generation_parallel,
    repeats: request.repeats,
    holdout_repeats: request.holdout_repeats,
    model: request.model,
    reasoning: request.reasoning,
    min_gain: request.min_gain,
    target_score: request.target_score,
    plateau_rounds: request.plateau_rounds,
    candidate_timeout_seconds: request.candidate_timeout_seconds,
    eval_timeout_seconds: request.eval_timeout_seconds,
    max_wall_seconds: request.max_wall_seconds,
    max_tokens: request.max_tokens,
    max_failures: request.max_failures,
    seed: request.seed,
    apply: request.apply,
    quiet: request.quiet,
    json: request.json,
  };
  const manifest = {
    schema: `${SCHEMA}.manifest`,
    experiment_id: basename(out),
    created_at: now(),
    source: { workspace, head: source.head },
    config,
    fingerprints: {
      task: sha256(config.task),
      details: sha256(config.details),
      eval_argv: sha256(jsonBytes(config.eval_argv)),
      holdout_argv: sha256(jsonBytes(config.holdout_argv)),
      mutable: sha256(jsonBytes(config.mutable)),
    },
    runtime: {
      node: process.version,
      platform: `${process.platform}-${process.arch}`,
      codex_sdk: "0.149.0",
      auth: "chatgpt-subscription",
    },
  };
  atomicWrite(manifestPath(out), manifest);
  const ledger = new Ledger(ledgerPath(out));
  const state = {
    schema: `${SCHEMA}.state`,
    experiment_id: manifest.experiment_id,
    status: "created",
    created_at: manifest.created_at,
    updated_at: manifest.created_at,
    round: 0,
    baseline: null,
    incumbent: null,
    plateau_rounds: 0,
    counts: { candidates: 0, kept: 0, rejected: 0, invalid: 0, crashed: 0 },
    usage: usageZero(),
    failures: 0,
    terminal_reason: null,
    applied: false,
    ledger_seq: 0,
    ledger_hash: null,
  };
  const context = { experiment: out, manifest, ledger, state, config, repo, abortController: new AbortController() };
  append(context, "experiment_created", {
    experiment_id: manifest.experiment_id,
    source_head: source.head,
    config_sha256: sha256(jsonBytes(config)),
  });
  return context;
}

async function assertRuntime(context) {
  // Fail before candidate generation if a required evaluator secret was not
  // rehydrated. Only names are stored in durable state; values come from this
  // controller process on each run/resume.
  requestedEnv(context.config.extra_env_keys);
  if (Number(process.versions.node.split(".")[0]) < 18) {
    throw new ClimbError("E_RUNTIME", `Codex SDK needs Node 18+; found ${process.version}`);
  }
  const auth = runSync(["codex", "login", "status"], { allowFailure: true, env: sanitizeEnv() });
  const authText = `${auth.stdout}\n${auth.stderr}`;
  if (auth.status !== 0 || !/Logged in using ChatGPT/i.test(authText)) {
    throw new ClimbError("E_AUTH", "Codex is not signed in with ChatGPT subscription access", 2,
      { next_action: "run `codex login`, choose ChatGPT, then rerun or resume" });
  }
  let sdk;
  try {
    sdk = await loadCodex();
  } catch (error) {
    throw new ClimbError("E_SDK", `Codex SDK is unavailable: ${error.message}`, 2,
      { next_action: "reinstall pi graph with npm available, then resume" });
  }
  if (typeof sdk.Codex !== "function") {
    throw new ClimbError("E_SDK", "Codex SDK does not export Codex", 2,
      { next_action: "reinstall pi graph, then resume" });
  }
  const source = context.manifest.source;
  if (gitText(source.workspace, ["rev-parse", "HEAD"]) !== source.head ||
      gitText(source.workspace, ["status", "--porcelain=v1", "--untracked-files=normal"])) {
    throw new ClimbError("E_DRIFT", "source repository changed after the experiment was created", 3);
  }
  if (gitText(context.repo, ["rev-parse", "refs/hill-climber/baseline"]) !== source.head) {
    throw new ClimbError("E_EVIDENCE", "internal baseline ref drifted", 3);
  }
}

async function prepareWorktree(context, worktree) {
  if (!context.config.setup_argv.length) return;
  const result = await runProcess(context.config.setup_argv, {
    cwd: worktree,
    env: sanitizeEnv({ ...requestedEnv(context.config.extra_env_keys),
      HILL_CLIMBER_PHASE: "setup" }),
    timeoutSeconds: context.config.eval_timeout_seconds,
    signal: context.abortController.signal,
  });
  if (result.code !== 0) {
    throw new ClimbError("E_SETUP", `setup command failed: ${bounded(result.stderr || result.stdout, 1200).trim()}`);
  }
}

async function evaluateCommit(context, commit, phase, id, argv, repeats) {
  const root = join(context.experiment, "evaluations", id, phase);
  const scores = [];
  const results = [];
  const worktree = join(context.experiment, "worktrees", `grade-${id}-${phase}`);
  addWorktree(context.repo, worktree, commit);
  try {
    await prepareWorktree(context, worktree);
    for (let repeat = 0; repeat < repeats; repeat += 1) {
      if (context.abortController.signal.aborted) throw new InterruptedError();
      const seed = Number(context.config.seed) + repeat;
      const started = process.hrtime.bigint();
      const result = await runProcess(argv, {
        cwd: worktree,
        env: sanitizeEnv({
          ...requestedEnv(context.config.extra_env_keys),
          HILL_CLIMBER_PHASE: phase,
          HILL_CLIMBER_SEED: String(seed),
          HILL_CLIMBER_CANDIDATE: id,
        }),
        timeoutSeconds: context.config.eval_timeout_seconds,
        signal: context.abortController.signal,
      });
      mkdirSync(root, { recursive: true });
      atomicWrite(join(root, `repeat-${repeat + 1}.stdout`), result.stdout);
      atomicWrite(join(root, `repeat-${repeat + 1}.stderr`), result.stderr);
      if (result.code !== 0) {
        throw new ClimbError("E_EVALUATOR", `${phase} evaluator exited ${result.code}: ${bounded(result.stderr || result.stdout, 1200).trim()}`);
      }
      const parsed = evaluatorResult(result.stdout, `${phase} evaluator`);
      const record = { ...parsed, repeat: repeat + 1, seed, wall_seconds: monotonicSeconds(started) };
      atomicWrite(join(root, `repeat-${repeat + 1}.json`), record);
      scores.push(parsed.score);
      results.push(record);
    }
  } finally {
    safeRemoveWorktree(context.repo, worktree);
  }
  const gates = {};
  for (const result of results) {
    for (const [name, passed] of Object.entries(result.gates)) gates[name] = (gates[name] ?? true) && passed;
  }
  const aggregate = {
    score: average(scores),
    low: Math.min(...scores),
    high: Math.max(...scores),
    scores,
    gates,
    gates_passed: allGatesPass(gates),
    details: results.map((result) => result.details).filter(Boolean),
    feedback: [...new Set(results.flatMap((result) => result.feedback))].slice(0, 40),
    metrics: results.map((result) => ({
      repeat: result.repeat,
      seed: result.seed,
      values: result.metrics,
    })),
  };
  atomicWrite(join(root, "aggregate.json"), aggregate);
  return aggregate;
}

function candidatePrompt(context, candidateId, round, index, parent, strategy, prior) {
  const [strategyId, strategyText] = strategy;
  const mutable = context.config.mutable.map((item) => `- ${item}`).join("\n");
  return `You are candidate ${index + 1}/${context.config.candidates} in round ${round} of a bounded hill climb.

Task:
${context.config.task}

Details:
${context.config.details || "No additional details."}

This worktree is an isolated copy of incumbent ${parent}. Make exactly one coherent mechanism change.
Strategy lane (${strategyId}): ${strategyText}

You may modify only paths matching:
${mutable}

Do not edit tests, evaluators, fixtures, Git metadata, package locks outside the mutable allowlist, or generated evidence. Do not use the network. You may run existing local checks. Do not special-case named tests or fabricate metrics. Keep the change focused and leave the worktree ready for an independent evaluator.

Visible development evidence from earlier completed work (never holdout data):
${prior || "Baseline only; inspect the code and local public checks."}

Reflect before editing: diagnose the general failure or success pattern in that evidence, identify one transferable mechanism, and avoid encoding visible case names, literal answers, or one-off branches. Preserve what already works.

When finished, return the required JSON with one mechanism identifier, a falsifiable hypothesis, and a concise summary. The controller ignores self-reported scores and grades the committed diff independently.`;
}

const CANDIDATE_SCHEMA = {
  type: "object",
  properties: {
    mechanism: { type: "string", minLength: 1, maxLength: 160 },
    hypothesis: { type: "string", minLength: 1, maxLength: 1000 },
    summary: { type: "string", minLength: 1, maxLength: 2000 },
  },
  required: ["mechanism", "hypothesis", "summary"],
  additionalProperties: false,
};

async function loadCodex() {
  const override = process.env.HILL_CLIMBER_CODEX_MODULE;
  if (override) {
    const url = override.startsWith("file:") ? override : pathToFileURL(resolve(override)).href;
    return await import(url);
  }
  return await import("@openai/codex-sdk");
}

async function runCodexCandidate(context, candidateId, round, index, worktree, prompt) {
  const module = await loadCodex();
  if (typeof module.Codex !== "function") throw new ClimbError("E_SDK", "Codex SDK module does not export Codex");
  // Codex needs HOME/CODEX_HOME for the cached ChatGPT login, but candidate
  // shells must not inherit unrelated API keys or CI secrets.
  const codex = new module.Codex({ env: sanitizeEnv() });
  const thread = codex.startThread({
    workingDirectory: worktree,
    sandboxMode: "workspace-write",
    approvalPolicy: "never",
    networkAccessEnabled: false,
    webSearchMode: "disabled",
    model: context.config.model,
    modelReasoningEffort: context.config.reasoning,
  });
  const deadline = AbortSignal.timeout(Math.max(1, context.config.candidate_timeout_seconds) * 1000);
  const signal = anySignal([context.abortController.signal, deadline]);
  const events = [];
  let finalResponse = "";
  let usage = null;
  let threadId = null;
  let turnCompleted = 0;
  let failure = null;
  try {
    const streamed = await thread.runStreamed(prompt, { outputSchema: CANDIDATE_SCHEMA, signal });
    for await (const event of streamed.events) {
      events.push(event);
      if (event.type === "thread.started") threadId = event.thread_id;
      if (event.type === "turn.completed") { usage = event.usage; turnCompleted += 1; }
      if (event.type === "turn.failed") failure = event.error?.message ?? "turn failed";
      if (event.type === "error") failure = event.message ?? "SDK stream error";
      if (event.type === "item.completed" && event.item?.type === "agent_message") {
        finalResponse = event.item.text;
      }
    }
  } catch (error) {
    if (signal.aborted) {
      if (context.abortController.signal.aborted) throw new InterruptedError();
      throw new ClimbError("E_CANDIDATE_TIMEOUT", `candidate ${candidateId} exceeded ${context.config.candidate_timeout_seconds}s`);
    }
    throw new ClimbError("E_SDK", `Codex candidate ${candidateId} failed: ${error.message}`);
  }
  const trace = { schema: `${SCHEMA}.codex-turn`, candidate_id: candidateId, thread_id: threadId, usage, events };
  const candidateDir = join(context.experiment, "candidates", candidateId);
  mkdirSync(candidateDir, { recursive: true });
  atomicWrite(join(candidateDir, "turn.json"), trace);
  if (failure) throw new ClimbError("E_SDK", `Codex candidate ${candidateId} failed: ${failure}`);
  if (!threadId || turnCompleted !== 1 || !usage || usageTotal(usage) <= 0 || !finalResponse.trim()) {
    throw new ClimbError("E_SDK_EMPTY", `Codex candidate ${candidateId} ended without a complete, metered response`);
  }
  let metadata;
  try { metadata = JSON.parse(finalResponse); }
  catch (error) { throw new ClimbError("E_SDK_SCHEMA", `candidate ${candidateId} response was not JSON: ${error.message}`); }
  for (const key of CANDIDATE_SCHEMA.required) {
    if (typeof metadata[key] !== "string" || !metadata[key].trim()) {
      throw new ClimbError("E_SDK_SCHEMA", `candidate ${candidateId} response omitted ${key}`);
    }
  }
  return { metadata, usage, thread_id: threadId, trace_sha256: fileSha256(join(candidateDir, "turn.json")) };
}

function priorEvidence(context) {
  const decisions = new Map();
  for (const record of context.ledger.records) {
    if (!["candidate_kept", "candidate_rejected"].includes(record.type)) continue;
    decisions.set(record.payload.candidate_id, {
      status: record.type === "candidate_kept" ? "kept" : "rejected",
      reason: record.payload.reason ?? "unspecified",
    });
  }
  const evaluated = context.ledger.records.filter((record) => record.type === "candidate_evaluated");
  const lineage = evaluated.filter((record) => decisions.get(record.payload.candidate_id)?.status === "kept").slice(-8);
  const recent = evaluated.slice(-10);
  const selected = [...new Map([...lineage, ...recent]
    .map((record) => [record.payload.candidate_id, record])).values()]
    .sort((left, right) => left.seq - right.seq);
  const lines = selected
    .map((record) => {
      const payload = record.payload;
      const metadata = payload.metadata ?? {};
      const evaluation = payload.evaluation ?? {};
      const decision = decisions.get(payload.candidate_id) ?? { status: "evaluated", reason: "pending" };
      const feedback = (evaluation.feedback ?? []).map((value) => safeLine(value)).filter(Boolean).join(" | ");
      const metrics = bounded(JSON.stringify(evaluation.metrics ?? []), 1200);
      return [
        `${payload.candidate_id} [${decision.status}:${decision.reason}]`,
        `strategy=${payload.strategy ?? "unknown"}`,
        `mechanism=${safeLine(metadata.mechanism ?? "unknown")}`,
        `hypothesis=${safeLine(metadata.hypothesis ?? "unknown")}`,
        `score=${evaluation.score}; gates=${evaluation.gates_passed}`,
        `diagnostics=${bounded(payload.details ?? "none", 500)}`,
        `actionable_feedback=${bounded(feedback || "none", 1200)}`,
        `metrics=${metrics}`,
      ].join("; ");
    });
  const failures = context.ledger.records
    .filter((record) => ["candidate_invalid", "candidate_crashed"].includes(record.type))
    .slice(-4)
    .map((record) => `${record.payload.candidate_id}: ${record.type}; code=${record.payload.code ?? "unknown"}; diagnostic=${bounded(record.payload.error ?? record.payload.reason ?? "none", 500)}`);
  const selections = context.ledger.records
    .filter((record) => record.type === "round_selected")
    .slice(-4)
    .map((record) => `round ${record.payload.round}: selected ${record.payload.selected_id ?? "incumbent"}; score=${record.payload.incumbent_score_after}`);
  return bounded([...lines, ...failures, ...selections].join("\n"), 12000);
}

async function generateCandidate(context, round, index, parent) {
  const candidateId = `r${String(round).padStart(2, "0")}-c${String(index + 1).padStart(2, "0")}`;
  const worktree = ensureInside(context.experiment, join(context.experiment, "worktrees", candidateId), "candidate worktree");
  const strategy = STRATEGIES[index % STRATEGIES.length];
  const candidateDir = join(context.experiment, "candidates", candidateId);
  mkdirSync(candidateDir, { recursive: true });
  append(context, "candidate_started", { candidate_id: candidateId, round, index: index + 1, parent, strategy: strategy[0] });
  progress(context.config, `CANDIDATE ${index + 1}/${context.config.candidates}`, `GENERATING ${candidateId} (${strategy[0]})`);
  const started = process.hrtime.bigint();
  let codex = null;
  try {
    addWorktree(context.repo, worktree, parent);
    await prepareWorktree(context, worktree);
    const prompt = candidatePrompt(context, candidateId, round, index, parent, strategy, priorEvidence(context));
    atomicWrite(join(candidateDir, "prompt.txt"), prompt);
    codex = await runCodexCandidate(context, candidateId, round, index, worktree, prompt);
    const debris = removeExecutionDebris(worktree);
    if (debris.length) append(context, "candidate_debris_removed", { candidate_id: candidateId, paths: debris });
    const paths = changedPaths(worktree);
    if (!paths.length) throw new ClimbError("E_NO_CHANGE", `candidate ${candidateId} changed no files`);
    const denied = paths.filter((path) => !pathAllowed(path, context.config.mutable));
    if (denied.length) {
      throw new ClimbError("E_MUTABLE_BOUNDARY", `candidate ${candidateId} changed forbidden paths: ${denied.join(", ")}`);
    }
    const commit = candidateCommit(worktree, candidateId);
    applyRef(context.repo, `candidates/${candidateId}`, commit);
    const diff = git(context.repo, ["diff", "--binary", parent, commit]).stdout;
    atomicWrite(join(candidateDir, "change.patch"), diff);
    const result = {
      candidate_id: candidateId,
      round,
      index: index + 1,
      parent,
      commit,
      strategy: strategy[0],
      paths,
      metadata: codex.metadata,
      thread_id: codex.thread_id,
      usage: codex.usage,
      trace_sha256: codex.trace_sha256,
      generation_wall_seconds: monotonicSeconds(started),
      status: "generated",
    };
    atomicWrite(join(candidateDir, "generated.json"), result);
    append(context, "candidate_generated", result);
    return result;
  } catch (error) {
    if (error instanceof InterruptedError) throw error;
    const classified = error instanceof ClimbError ? error : new ClimbError("E_CANDIDATE", error.message);
    const status = ["E_NO_CHANGE", "E_MUTABLE_BOUNDARY", "E_SDK_SCHEMA"].includes(classified.code) ? "invalid" : "crashed";
    context.state.counts[status] += 1;
    context.state.counts.candidates += 1;
    context.state.failures += 1;
    addUsage(context.state.usage, codex?.usage);
    append(context, status === "invalid" ? "candidate_invalid" : "candidate_crashed", {
      candidate_id: candidateId,
      round,
      index: index + 1,
      code: classified.code,
      error: bounded(classified.message),
      usage: codex?.usage ?? null,
      wall_seconds: monotonicSeconds(started),
    });
    atomicWrite(join(candidateDir, "failure.json"), {
      schema: `${SCHEMA}.candidate-failure`, code: classified.code, message: classified.message, at: now(),
    });
    progress(context.config, `CANDIDATE ${index + 1}/${context.config.candidates}`, `${status.toUpperCase()} ${classified.code}: ${bounded(classified.message, 240)}`);
    return { candidate_id: candidateId, round, index: index + 1, status, error: classified.message };
  } finally {
    safeRemoveWorktree(context.repo, worktree);
  }
}

async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let cursor = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (true) {
      const index = cursor;
      cursor += 1;
      if (index >= items.length) return;
      results[index] = await fn(items[index], index);
    }
  });
  await Promise.all(workers);
  return results;
}

async function evaluateCandidates(context, generated) {
  const evaluated = [];
  for (const candidate of generated) {
    if (candidate.status !== "generated") continue;
    const { candidate_id: candidateId, commit } = candidate;
    const index = candidate.index;
    progress(context.config, `CANDIDATE ${index}/${context.config.candidates}`, `EVALUATING ${candidateId}`);
    const started = process.hrtime.bigint();
    try {
      const evaluation = await evaluateCommit(
        context, commit, "development", candidateId,
        context.config.eval_argv, context.config.repeats,
      );
      const complexity = candidateComplexity(context.repo, context.manifest.source.head, commit);
      const result = {
        ...candidate,
        evaluation,
        complexity,
        evaluation_wall_seconds: monotonicSeconds(started),
        status: "evaluated",
      };
      atomicWrite(join(context.experiment, "candidates", candidateId, "result.json"), result);
      context.state.counts.candidates += 1;
      addUsage(context.state.usage, candidate.usage);
      append(context, "candidate_evaluated", {
        candidate_id: candidateId,
        round: candidate.round,
        parent: candidate.parent,
        commit,
        strategy: candidate.strategy,
        metadata: candidate.metadata,
        evaluation,
        complexity,
        usage: candidate.usage,
        details: bounded(evaluation.details.join(" "), 1200),
      });
      evaluated.push(result);
      progress(context.config, `CANDIDATE ${index}/${context.config.candidates}`,
        `SCORED ${evaluation.score.toFixed(6)} gates=${evaluation.gates_passed ? "pass" : "fail"}`);
    } catch (error) {
      if (error instanceof InterruptedError) throw error;
      const classified = error instanceof ClimbError ? error : new ClimbError("E_EVALUATOR", error.message);
      context.state.counts.crashed += 1;
      context.state.counts.candidates += 1;
      context.state.failures += 1;
      addUsage(context.state.usage, candidate.usage);
      append(context, "candidate_crashed", {
        candidate_id: candidateId,
        round: candidate.round,
        index,
        code: classified.code,
        error: bounded(classified.message),
        phase: "evaluation",
      });
      atomicWrite(join(context.experiment, "candidates", candidateId, "failure.json"), {
        schema: `${SCHEMA}.candidate-failure`, code: classified.code, message: classified.message, at: now(),
      });
      progress(context.config, `CANDIDATE ${index}/${context.config.candidates}`,
        `CRASHED ${classified.code}: ${bounded(classified.message, 240)}`);
    }
    if (context.state.failures >= context.config.max_failures) break;
  }
  return evaluated;
}

function compareCandidate(candidate, incumbent, config) {
  if (!candidate.evaluation.gates_passed) return { eligible: false, reason: "hard_gate_failed" };
  const delta = candidate.evaluation.score - incumbent.score;
  const robust = candidate.evaluation.low >= incumbent.low - Number.EPSILON;
  const strictGain = delta >= config.min_gain && delta > 0;
  const tieSimpler = Math.abs(delta) <= Number.EPSILON &&
    candidate.complexity.lines < incumbent.complexity.lines;
  if (strictGain && robust) return { eligible: true, delta, reason: "strict_gain" };
  if (tieSimpler && robust) return { eligible: true, delta, reason: "equal_but_simpler" };
  return { eligible: false, delta, reason: robust ? "insufficient_gain" : "repeat_regression" };
}

function selectRound(context, round, candidates) {
  const incumbent = context.state.incumbent;
  const ranked = candidates.map((candidate) => ({
    candidate,
    decision: compareCandidate(candidate, incumbent, context.config),
  })).sort((left, right) => {
    if (left.decision.eligible !== right.decision.eligible) return left.decision.eligible ? -1 : 1;
    if (right.candidate.evaluation.score !== left.candidate.evaluation.score) {
      return right.candidate.evaluation.score - left.candidate.evaluation.score;
    }
    if (left.candidate.complexity.lines !== right.candidate.complexity.lines) {
      return left.candidate.complexity.lines - right.candidate.complexity.lines;
    }
    return left.candidate.candidate_id.localeCompare(right.candidate.candidate_id);
  });
  const winner = ranked.find((entry) => entry.decision.eligible) ?? null;
  for (const entry of ranked) {
    const kept = winner?.candidate.candidate_id === entry.candidate.candidate_id;
    if (kept) context.state.counts.kept += 1;
    else context.state.counts.rejected += 1;
    append(context, kept ? "candidate_kept" : "candidate_rejected", {
      candidate_id: entry.candidate.candidate_id,
      round,
      score: entry.candidate.evaluation.score,
      incumbent_score: incumbent.score,
      delta: entry.decision.delta ?? null,
      reason: kept ? entry.decision.reason : (entry.decision.eligible ? "lower_ranked_than_round_winner" : entry.decision.reason),
      rollback: kept ? "not_applicable" : "isolated_worktree_discarded",
    });
    progress(context.config, `CANDIDATE ${entry.candidate.index}/${context.config.candidates}`,
      `${kept ? "KEPT" : "REJECTED"} ${entry.candidate.candidate_id} score=${entry.candidate.evaluation.score.toFixed(6)} reason=${kept ? entry.decision.reason : (entry.decision.eligible ? "lower_ranked_than_round_winner" : entry.decision.reason)}`);
  }
  if (winner) {
    applyRef(context.repo, "incumbent", winner.candidate.commit);
    context.state.incumbent = {
      id: winner.candidate.candidate_id,
      commit: winner.candidate.commit,
      score: winner.candidate.evaluation.score,
      low: winner.candidate.evaluation.low,
      high: winner.candidate.evaluation.high,
      scores: winner.candidate.evaluation.scores,
      gates: winner.candidate.evaluation.gates,
      complexity: winner.candidate.complexity,
    };
    context.state.plateau_rounds = 0;
  } else {
    context.state.plateau_rounds += 1;
  }
  append(context, "round_selected", {
    round,
    selected_id: winner?.candidate.candidate_id ?? null,
    selected_commit: winner?.candidate.commit ?? incumbent.commit,
    incumbent_score_before: incumbent.score,
    incumbent_score_after: context.state.incumbent.score,
    candidates: ranked.map((entry) => ({
      id: entry.candidate.candidate_id,
      score: entry.candidate.evaluation.score,
      gates_passed: entry.candidate.evaluation.gates_passed,
      eligible: entry.decision.eligible,
      reason: entry.decision.reason,
    })),
  });
  progress(context.config, `ROUND ${round}`,
    winner ? `KEPT ${winner.candidate.candidate_id} ${incumbent.score.toFixed(6)} -> ${context.state.incumbent.score.toFixed(6)}`
      : `RETAINED ${incumbent.id} score=${incumbent.score.toFixed(6)}`);
  return winner;
}

function stopReason(context) {
  const elapsed = (Date.now() - Date.parse(context.manifest.created_at)) / 1000;
  if (existsSync(join(context.experiment, "stop.request"))) return "stop_requested";
  if (elapsed >= context.config.max_wall_seconds) return "wall_budget_exhausted";
  if (usageTotal(context.state.usage) >= context.config.max_tokens) return "token_budget_exhausted";
  if (context.state.failures >= context.config.max_failures) return "failure_budget_exhausted";
  if (context.config.target_score !== null && context.config.target_score !== undefined &&
      context.state.incumbent?.score >= context.config.target_score) return "target_achieved";
  if (context.state.plateau_rounds >= context.config.plateau_rounds) return "plateau";
  if (context.state.round >= context.config.rounds) return "round_budget_exhausted";
  return null;
}

function pendingRound(context) {
  const completed = new Set(context.ledger.records
    .filter((record) => record.type === "round_selected")
    .map((record) => Number(record.payload.round)));
  const started = context.ledger.records
    .filter((record) => record.type === "round_started" && !completed.has(Number(record.payload.round)));
  return started.length ? started.at(-1).payload : null;
}

function candidateArtifact(context, round, index) {
  const candidateId = `r${String(round).padStart(2, "0")}-c${String(index + 1).padStart(2, "0")}`;
  const directory = join(context.experiment, "candidates", candidateId);
  const resultPath = join(directory, "result.json");
  const generatedPath = join(directory, "generated.json");
  const failurePath = join(directory, "failure.json");
  if (existsSync(resultPath)) return readJson(resultPath);
  if (existsSync(generatedPath)) return readJson(generatedPath);
  if (existsSync(failurePath)) {
    const failure = readJson(failurePath);
    return { candidate_id: candidateId, round, index: index + 1, status: "failed", error: failure.message };
  }
  return null;
}

function holdoutRecord(context, type) {
  return context.ledger.records.filter((record) => record.type === type).at(-1) ?? null;
}

async function baseline(context) {
  if (context.state.baseline) return;
  progress(context.config, "BASELINE", `EVALUATING ${context.manifest.source.head.slice(0, 12)}`);
  context.state.status = "baseline_running";
  append(context, "baseline_started", { commit: context.manifest.source.head });
  const evaluation = await evaluateCommit(
    context, context.manifest.source.head, "development", "baseline",
    context.config.eval_argv, context.config.repeats,
  );
  if (!evaluation.gates_passed) throw new ClimbError("E_BASELINE_GATE", "untouched baseline failed a hard evaluator gate");
  const value = {
    id: "baseline",
    commit: context.manifest.source.head,
    score: evaluation.score,
    low: evaluation.low,
    high: evaluation.high,
    scores: evaluation.scores,
    gates: evaluation.gates,
    complexity: { files: 0, lines: 0 },
  };
  context.state.baseline = value;
  context.state.incumbent = { ...value };
  context.state.status = "searching";
  append(context, "baseline_evaluated", { ...value, evaluation });
  progress(context.config, "BASELINE", `SCORE ${value.score.toFixed(6)} gates=pass`);
}

async function runRound(context, round, recovery = null) {
  context.state.round = round;
  const parent = recovery?.parent ?? context.state.incumbent.commit;
  if (!recovery) {
    append(context, "round_started", {
      round,
      parent,
      parent_id: context.state.incumbent.id,
      candidates: context.config.candidates,
    });
  } else {
    append(context, "round_recovery_started", { round, parent });
  }
  const indexes = Array.from({ length: context.config.candidates }, (_, index) => index);
  const artifacts = indexes.map((index) => candidateArtifact(context, round, index));
  const missing = indexes.filter((index) => artifacts[index] === null);
  const regenerated = await mapLimit(missing, context.config.generation_parallel,
    async (index) => await generateCandidate(context, round, index, parent));
  for (let cursor = 0; cursor < missing.length; cursor += 1) artifacts[missing[cursor]] = regenerated[cursor];
  if (context.abortController.signal.aborted) throw new InterruptedError();
  const alreadyEvaluated = artifacts.filter((candidate) => candidate?.status === "evaluated");
  const newlyEvaluated = await evaluateCandidates(context,
    artifacts.filter((candidate) => candidate?.status === "generated"));
  const evaluated = [...alreadyEvaluated, ...newlyEvaluated];
  if (!evaluated.length) {
    context.state.plateau_rounds += 1;
    append(context, "round_selected", {
      round, selected_id: null, selected_commit: parent,
      incumbent_score_before: context.state.incumbent.score,
      incumbent_score_after: context.state.incumbent.score,
      candidates: [], reason: "no_valid_evaluations",
    });
    progress(context.config, `ROUND ${round}`, `RETAINED ${context.state.incumbent.id}; no valid candidate evaluation`);
    return;
  }
  selectRound(context, round, evaluated);
}

async function promotion(context) {
  const baselineValue = context.state.baseline;
  const incumbent = context.state.incumbent;
  if (incumbent.id === "baseline") {
    context.state.status = "retained";
    context.state.terminal_reason = context.state.terminal_reason ?? "no_development_winner";
    append(context, "promotion_skipped", { reason: "no_development_winner", holdout_used: false });
    return { verdict: "retained", holdout_used: false };
  }
  context.state.status = "holdout_running";
  append(context, "holdout_started", { baseline: baselineValue.commit, candidate: incumbent.commit });
  progress(context.config, "HOLDOUT", `EVALUATING baseline and ${incumbent.id}`);
  const holdoutBaseline = await evaluateCommit(
    context, baselineValue.commit, "holdout", "holdout-baseline",
    context.config.holdout_argv, context.config.holdout_repeats,
  );
  const holdoutCandidate = await evaluateCommit(
    context, incumbent.commit, "holdout", "holdout-candidate",
    context.config.holdout_argv, context.config.holdout_repeats,
  );
  const delta = holdoutCandidate.score - holdoutBaseline.score;
  const passed = holdoutBaseline.gates_passed && holdoutCandidate.gates_passed &&
    delta >= context.config.min_gain && delta > 0 &&
    holdoutCandidate.low >= holdoutBaseline.low - Number.EPSILON;
  const result = {
    verdict: passed ? "promoted" : "reverted",
    holdout_used: true,
    holdout_independent: context.config.holdout_independent !== false,
    baseline: holdoutBaseline,
    candidate: holdoutCandidate,
    delta,
  };
  context.state.status = passed ? "promoted" : "retained";
  if (!passed) {
    applyRef(context.repo, "incumbent", baselineValue.commit);
    context.state.incumbent = { ...baselineValue };
  }
  append(context, "holdout_completed", result);
  progress(context.config, "HOLDOUT",
    `${passed ? "PROMOTED" : "REVERTED"} delta=${delta.toFixed(6)} gates=${holdoutCandidate.gates_passed ? "pass" : "fail"}`);
  return result;
}

function applyWinner(context) {
  if (context.state.status !== "promoted") return null;
  const existingPatch = join(context.experiment, "winner.patch");
  if (context.state.applied) {
    if (!existsSync(existingPatch)) throw new ClimbError("E_EVIDENCE", "applied winner is missing winner.patch", 3);
    return existingPatch;
  }
  const source = context.manifest.source;
  assertCleanRepository(source.workspace);
  if (gitText(source.workspace, ["rev-parse", "HEAD"]) !== source.head) {
    throw new ClimbError("E_DRIFT", "source HEAD changed before apply", 3);
  }
  const patch = git(context.repo, ["diff", "--binary", source.head, context.state.incumbent.commit]).stdout;
  const patchPath = join(context.experiment, "winner.patch");
  atomicWrite(patchPath, patch);
  if (!patch.trim()) throw new ClimbError("E_APPLY", "promoted candidate has an empty patch");
  append(context, "winner_patch_prepared", {
    patch: relative(context.experiment, patchPath),
    patch_sha256: fileSha256(patchPath),
  });
  if (!context.config.apply) return patchPath;
  runSync(["git", "apply", "--check", patchPath], { cwd: source.workspace });
  runSync(["git", "apply", patchPath], { cwd: source.workspace });
  context.state.applied = true;
  append(context, "winner_applied", {
    workspace: source.workspace,
    patch: relative(context.experiment, patchPath),
    patch_sha256: fileSha256(patchPath),
  });
  return patchPath;
}

function reportCandidates(context) {
  const candidates = new Map();
  for (const record of context.ledger.records) {
    const payload = record.payload ?? {};
    const candidateId = payload.candidate_id;
    if (!candidateId) continue;
    const candidate = candidates.get(candidateId) ?? {
      id: candidateId,
      round: payload.round ?? null,
      index: payload.index ?? null,
      strategy: null,
      score: null,
      gates: null,
      status: "started",
      reason: null,
    };
    if (record.type === "candidate_started") candidate.strategy = payload.strategy;
    if (record.type === "candidate_evaluated") {
      candidate.score = payload.evaluation?.score ?? null;
      candidate.gates = payload.evaluation?.gates_passed ?? null;
      candidate.status = "evaluated";
    }
    if (record.type === "candidate_kept") {
      candidate.status = "kept";
      candidate.reason = payload.reason ?? null;
    }
    if (record.type === "candidate_rejected") {
      candidate.status = "rejected";
      candidate.reason = payload.reason ?? null;
    }
    if (record.type === "candidate_invalid" || record.type === "candidate_crashed") {
      candidate.status = record.type === "candidate_invalid" ? "invalid" : "crashed";
      candidate.reason = payload.code ?? payload.error ?? null;
    }
    candidates.set(candidateId, candidate);
  }
  return [...candidates.values()].sort((left, right) => left.id.localeCompare(right.id));
}

function renderReport(context, receipt) {
  const allCandidates = reportCandidates(context);
  const kept = context.ledger.records.filter((record) => record.type === "candidate_kept").at(-1)?.payload ?? null;
  const selectedId = kept?.candidate_id ?? null;
  const selected = allCandidates.find((candidate) => candidate.id === selectedId) ?? null;
  const keptCount = allCandidates.filter((candidate) => candidate.status === "kept").length;
  const roundIds = [...new Set(allCandidates.map((candidate) => Number(candidate.round)))]
    .filter(Number.isFinite).sort((left, right) => left - right);
  const roundNoun = roundIds.length === 1 ? "round" : "rounds";
  const climbNoun = keptCount === 1 ? "verified climb" : "verified climbs";
  const height = 820;
  const promoted = receipt.status === "promoted";
  const accent = promoted ? "#32d583" : "#f5b942";
  const statusLabel = promoted ? "PROMOTED" : "RETAINED";
  const holdout = receipt.promotion?.holdout_used
    ? String(receipt.promotion.verdict ?? "complete").toUpperCase()
    : "NOT RUN";
  const holdoutBaseline = receipt.promotion?.baseline?.score;
  const holdoutCandidate = receipt.promotion?.candidate?.score;
  const developmentWinner = selected?.score ?? (selectedId ? kept?.score : receipt.baseline.score);

  const chart = { left: 100, right: 1132, top: 228, bottom: 492 };
  const scores = [receipt.baseline.score, ...allCandidates.map((candidate) => candidate.score)]
    .map(Number).filter(Number.isFinite);
  let scoreMin = Math.min(...scores);
  let scoreMax = Math.max(...scores);
  if (scoreMin === scoreMax) {
    const padding = Math.max(1, Math.abs(scoreMin) * 0.1);
    scoreMin -= padding;
    scoreMax += padding;
  } else {
    const padding = (scoreMax - scoreMin) * 0.12;
    scoreMin -= padding;
    scoreMax += padding;
  }
  const xFor = (index) => chart.left + ((chart.right - chart.left) * index / Math.max(1, allCandidates.length));
  const yFor = (score) => chart.bottom - ((Number(score) - scoreMin) / (scoreMax - scoreMin)) * (chart.bottom - chart.top);

  const roundBands = roundIds.map((round, roundIndex) => {
    const indexes = allCandidates.map((candidate, index) => Number(candidate.round) === round ? index : -1)
      .filter((index) => index >= 0);
    const first = indexes[0];
    const last = indexes.at(-1);
    const left = first === 0 ? chart.left : (xFor(first) + xFor(first + 1)) / 2;
    const right = last === allCandidates.length - 1
      ? chart.right
      : (xFor(last + 1) + xFor(last + 2)) / 2;
    return `<rect x="${left}" y="${chart.top}" width="${right - left}" height="${chart.bottom - chart.top}" fill="${roundIndex % 2 === 0 ? "#111f34" : "#0b1526"}" fill-opacity=".52"/>
      <text x="${(left + right) / 2}" y="${chart.top + 18}" class="round" text-anchor="middle">ROUND ${round}</text>`;
  }).join("\n");

  const grid = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const y = chart.bottom - ratio * (chart.bottom - chart.top);
    const value = scoreMin + ratio * (scoreMax - scoreMin);
    return `<line x1="${chart.left}" y1="${y}" x2="${chart.right}" y2="${y}" class="grid"/>
    <text x="${chart.left - 14}" y="${y + 4}" class="axis" text-anchor="end">${xml(scoreText(value))}</text>`;
  }).join("\n");

  const roundAfter = new Map(context.ledger.records
    .filter((record) => record.type === "round_selected")
    .map((record) => [Number(record.payload.round), Number(record.payload.incumbent_score_after)]));
  const roundBefore = new Map(context.ledger.records
    .filter((record) => record.type === "round_selected")
    .map((record) => [Number(record.payload.round), Number(record.payload.incumbent_score_before)]));
  const firstIndexByRound = new Map();
  allCandidates.forEach((candidate, index) => {
    const round = Number(candidate.round);
    if (!firstIndexByRound.has(round)) firstIndexByRound.set(round, index);
  });
  const routeEdges = allCandidates.map((candidate, index) => {
    if (!Number.isFinite(Number(candidate.score))) return "";
    const round = Number(candidate.round);
    const firstIndex = firstIndexByRound.get(round) ?? 0;
    const parentX = xFor(firstIndex);
    const parentY = yFor(roundBefore.get(round) ?? receipt.baseline.score);
    const candidateX = xFor(index + 1);
    const candidateY = yFor(candidate.score);
    const keptRoute = candidate.status === "kept";
    return `<line data-candidate="${xml(candidate.id)}" class="route ${keptRoute ? "route-kept" : "route-rejected"}" x1="${parentX}" y1="${parentY}" x2="${candidateX}" y2="${candidateY}"/>`;
  }).join("\n");
  let incumbentScore = Number(receipt.baseline.score);
  let incumbentPath = `M ${xFor(0)} ${yFor(incumbentScore)}`;
  for (let index = 0; index < allCandidates.length; index += 1) {
    const candidate = allCandidates[index];
    const x = xFor(index + 1);
    incumbentPath += ` H ${x}`;
    const next = allCandidates[index + 1];
    const endsRound = !next || Number(next.round) !== Number(candidate.round);
    if (endsRound && roundAfter.has(Number(candidate.round))) {
      incumbentScore = roundAfter.get(Number(candidate.round));
      incumbentPath += ` V ${yFor(incumbentScore)}`;
    }
  }
  const incumbentAreaPath = `${incumbentPath} L ${xFor(allCandidates.length)} ${chart.bottom} L ${xFor(0)} ${chart.bottom} Z`;

  const attemptTicks = allCandidates.map((candidate, index) => {
    const stride = Math.max(1, Math.ceil(allCandidates.length / 10));
    if ((index + 1) % stride !== 0 && index !== 0 && index !== allCandidates.length - 1) return "";
    return `<text x="${xFor(index + 1)}" y="${chart.bottom + 25}" class="axis" text-anchor="middle">${index + 1}</text>`;
  }).join("");

  const candidateMarks = allCandidates.map((candidate, index) => {
    const x = xFor(index + 1);
    if (!Number.isFinite(Number(candidate.score))) {
      return `<path d="M ${x - 5} ${chart.bottom - 5}l10 10m0-10l-10 10" stroke="#f97066" stroke-width="2"/>`;
    }
    const y = yFor(candidate.score);
    const isSelected = candidate.id === selectedId;
    const isKept = candidate.status === "kept";
    const color = isKept ? "#32d583" : candidate.gates === false ? "#f5b942" : "#66758d";
    const calloutBelow = y < chart.top + 52;
    const calloutY = calloutBelow ? y + 34 : Math.max(chart.top + 18, y - 22);
    const calloutStart = calloutBelow ? y + 9 : y - 9;
    const calloutEnd = calloutBelow ? calloutY - 12 : calloutY + 5;
    const labelAnchor = x > chart.right - 150 ? "end" : x < chart.left + 150 ? "start" : "middle";
    const labelX = labelAnchor === "end" ? chart.right - 8 : labelAnchor === "start" ? chart.left + 8 : x;
    const keptLabel = isSelected ? "DEV WINNER" : "KEPT";
    return `<circle cx="${x}" cy="${y}" r="${isKept ? 7 : 5}" fill="${color}" stroke="#081120" stroke-width="2"/>${isKept ? `
      <path d="M ${x} ${calloutStart}V ${calloutEnd}" stroke="#32d583" stroke-width="1"/>
      <text x="${labelX}" y="${calloutY}" class="selected" text-anchor="${labelAnchor}">${keptLabel} · ${xml(candidate.id)} · ${xml(scoreText(candidate.score))}</text>` : ""}`;
  }).join("\n");

  const task = xml(shortLine(receipt.task, 128));
  const verdictDetail = receipt.promotion?.holdout_used
    ? `baseline ${scoreText(holdoutBaseline)} → candidate ${scoreText(holdoutCandidate)}`
    : "No development winner reached the private holdout";
  const applied = receipt.applied ? "YES — PATCH APPLIED" : promoted ? "NO — PATCH SAVED" : "NO — BASELINE KEPT";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="${height}" viewBox="0 0 1200 ${height}" role="img" aria-labelledby="title desc">
  <title id="title">Hill Climber result: ${xml(statusLabel.toLowerCase())}</title>
  <desc id="desc">A multi-round hill climb showing every candidate, rejected routes, verified incumbent steps, private holdout verdict, usage, and application state.</desc>
  <style>
    text { font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .eyebrow { fill: #32d583; font-size: 13px; font-weight: 800; letter-spacing: 2.2px; }
    .title { fill: #f7f9fc; font-size: 34px; font-weight: 760; }
    .task { fill: #aab4c5; font-size: 15px; }
    .label { font-size: 11px; font-weight: 800; letter-spacing: 1.2px; }
    .muted { fill: #8b98ad; font-size: 12px; }
    .score { fill: #f7f9fc; font-size: 32px; font-weight: 760; }
    .body { fill: #c6cfdd; font-size: 15px; }
    .metric { fill: #f7f9fc; font-size: 17px; font-weight: 700; }
    .axis { fill: #718096; font-size: 11px; }
    .round { fill: #5f718c; font-size: 10px; font-weight: 800; letter-spacing: 1.4px; }
    .grid { stroke: #26344c; stroke-width: 1; stroke-dasharray: 3 5; }
    .route { fill: none; }
    .route-rejected { stroke: #66758d; stroke-width: 1.25; stroke-dasharray: 4 4; stroke-opacity: .48; }
    .route-kept { stroke: #32d583; stroke-width: 2; stroke-opacity: .72; }
    .selected { fill: #32d583; font-size: 10px; font-weight: 800; letter-spacing: .6px; }
  </style>
  <rect width="1200" height="${height}" rx="24" fill="#081120"/>
  <path d="M0 0h1200v6H0z" fill="${accent}"/>
  <text x="40" y="48" class="eyebrow">HILL CLIMBER · VERIFIED RUN REPORT</text>
  <text x="40" y="92" class="title">${roundIds.length} ${roundNoun}. ${keptCount} ${climbNoun}.</text>
  <rect x="1016" y="35" width="144" height="42" rx="21" fill="${accent}" fill-opacity=".13" stroke="${accent}"/>
  <text x="1088" y="61" class="label" fill="${accent}" text-anchor="middle">${xml(statusLabel)}</text>
  <text x="40" y="124" class="task">${task}</text>

  <rect x="40" y="154" width="1120" height="402" rx="18" fill="#0d1728" stroke="#26344c"/>
  <text x="64" y="188" class="label" fill="#8b98ad">VERIFIED HILL-CLIMB TRAJECTORY</text>
  <line x1="786" y1="184" x2="818" y2="184" stroke="#32d583" stroke-width="4"/>
  <text x="826" y="188" class="axis">best verified</text>
  <circle cx="966" cy="184" r="5" fill="#66758d"/>
  <text x="978" y="188" class="axis">rejected</text>
  <circle cx="1054" cy="184" r="6" fill="#32d583"/>
  <text x="1066" y="188" class="axis">kept</text>
  ${roundBands}
  ${grid}
  <path d="${incumbentAreaPath}" fill="#32d583" fill-opacity=".07"/>
  ${routeEdges}
  <path d="${incumbentPath}" fill="none" stroke="#32d583" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="${xFor(0)}" cy="${yFor(receipt.baseline.score)}" r="6" fill="#58a6ff" stroke="#081120" stroke-width="2"/>
  ${candidateMarks}
  ${attemptTicks}
  <text x="${chart.left}" y="${chart.bottom + 25}" class="axis" text-anchor="middle">0</text>
  <text x="${(chart.left + chart.right) / 2}" y="${chart.bottom + 47}" class="axis" text-anchor="middle">candidate attempt · grouped by round</text>

  <rect x="40" y="580" width="710" height="166" rx="18" fill="#0d1728" stroke="${accent}" stroke-opacity=".8"/>
  <circle cx="72" cy="618" r="10" fill="${accent}"/>
  <text x="96" y="625" class="metric">${promoted ? "Holdout verified the winner" : "The baseline was safely retained"}</text>
  <text x="64" y="657" class="body">${promoted ? "The promoted patch cleared development selection and the private holdout." : "No candidate was applied because the final promotion boundary did not pass."}</text>
  <text x="64" y="690" class="label" fill="#8b98ad">PRIVATE HOLDOUT</text>
  <text x="214" y="690" class="metric" fill="${accent}">${xml(holdout)}</text>
  <text x="64" y="718" class="muted">${xml(verdictDetail)}</text>

  <rect x="774" y="580" width="386" height="166" rx="18" fill="#0d1728" stroke="#26344c"/>
  <text x="798" y="614" class="label" fill="#8b98ad">BASELINE → DEV WINNER</text>
  <text x="798" y="647" class="metric">${xml(scoreText(receipt.baseline.score))} → ${xml(scoreText(developmentWinner))}</text>
  <text x="798" y="678" class="label" fill="#8b98ad">SOURCE</text>
  <text x="868" y="678" class="metric">${xml(applied)}</text>
  <text x="798" y="709" class="muted">${receipt.counts.candidates} candidates · ${receipt.counts.kept} kept · ${receipt.counts.rejected} rejected</text>
  <text x="798" y="731" class="muted">${usageTotal(receipt.usage)} tokens · ${receipt.wall_seconds}s · ${receipt.rounds_completed} rounds</text>
  <text x="40" y="${height - 24}" class="muted">experiment ${xml(receipt.experiment_id)} · ${xml(receipt.completed_at)} · machine receipt: receipt.json</text>
</svg>\n`;
}

function makeReceipt(context, promotionResult, patchPath) {
  if (context.ledger.records.at(-1)?.type !== "receipt_prepared") {
    append(context, "receipt_prepared", {
      status: context.state.status,
      incumbent: context.state.incumbent.id,
      applied: context.state.applied,
    });
  }
  const receipt = {
    schema: `${SCHEMA}.receipt`,
    experiment_id: context.manifest.experiment_id,
    status: context.state.status,
    terminal_reason: context.state.terminal_reason,
    task: context.config.task,
    source: context.manifest.source,
    baseline: context.state.baseline,
    incumbent: context.state.incumbent,
    promotion: promotionResult,
    counts: context.state.counts,
    usage: context.state.usage,
    candidates_requested: context.config.candidates * context.state.round,
    rounds_completed: context.state.round,
    applied: context.state.applied,
    patch: patchPath ? { path: patchPath, sha256: fileSha256(patchPath) } : null,
    evidence: {
      manifest: { path: manifestPath(context.experiment), sha256: fileSha256(manifestPath(context.experiment)) },
      ledger: { path: ledgerPath(context.experiment), sha256: fileSha256(ledgerPath(context.experiment)) },
    },
    wall_seconds: Number(((Date.now() - Date.parse(context.manifest.created_at)) / 1000).toFixed(3)),
    completed_at: now(),
  };
  const reportPath = join(context.experiment, "report.svg");
  atomicWrite(reportPath, renderReport(context, receipt));
  receipt.report = { path: reportPath, sha256: fileSha256(reportPath), format: "image/svg+xml" };
  const path = join(context.experiment, "receipt.json");
  atomicWrite(path, receipt);
  return receipt;
}

// A holdout only proves generalization if candidates cannot read it and it is
// not literally the development evaluator. Neither property was enforced, so a
// repository-tracked holdout, or an identical dev/holdout command, could still
// report `promoted`. These checks run before any candidate is generated.
function assertEvaluatorHygiene(context) {
  const config = context.config;
  const workspace = context.manifest.source.workspace;

  const tracked = new Set(
    gitText(workspace, ["ls-files", "-z"]).split("\0").filter(Boolean),
  );

  // Compare canonical paths: on macOS a temp workspace resolves through the
  // /var -> /private/var symlink, and a lexical compare would treat an
  // in-repository holdout as outside the repository.
  const canonical = (path) => {
    try { return realpathSync(path); } catch { return resolve(path); }
  };
  const canonicalWorkspace = canonical(workspace);

  const exposed = [];
  for (const argument of config.holdout_argv) {
    if (typeof argument !== "string" || !argument) continue;
    const argumentPath = isAbsolute(argument) ? argument : resolve(workspace, argument);
    if (!existsSync(argumentPath)) continue;
    const relativeToWorkspace = relative(canonicalWorkspace, canonical(argumentPath));
    if (relativeToWorkspace && !relativeToWorkspace.startsWith("..") &&
        !isAbsolute(relativeToWorkspace) &&
        tracked.has(normalizePath(relativeToWorkspace))) {
      exposed.push(normalizePath(relativeToWorkspace));
    }
  }
  if (exposed.length) {
    throw new ClimbError("E_HOLDOUT_EXPOSED",
      `holdout evaluator is tracked inside the source repository: ${exposed.join(", ")}`, 2,
      { next_action: "move the holdout evaluator and its data outside the repository, then rerun" });
  }

  const suspicious = [...tracked].filter((path) => /holdout/i.test(path)).sort();
  if (suspicious.length) {
    progress(config, "WARNING",
      `${suspicious.length} tracked path(s) match "holdout" and are visible to every candidate: ` +
      `${bounded(suspicious.join(", "), 300)}`);
  }

  if (!config.holdout_independent) {
    progress(config, "WARNING",
      "holdout command is identical to the development command; promotion cannot detect overfitting");
  }

  // With a single repeat, low === high === score, so the repeat-robustness gate
  // (candidate.low >= incumbent.low) carries no variance information and any
  // positive delta promotes -- including measurement noise.
  if (config.repeats <= 1 || config.holdout_repeats <= 1) {
    progress(config, "WARNING",
      `repeats=${config.repeats} holdout_repeats=${config.holdout_repeats} min_gain=${config.min_gain}: ` +
      "the repeat-robustness gate is inert and noise can be promoted; " +
      "for timing evaluators use --repeats 3+ --holdout-repeats 3+ and a --min-gain above your noise floor");
  }
}

async function execute(context) {
  await assertRuntime(context);
  assertEvaluatorHygiene(context);
  progress(context.config, "CLIMB", `${context.experiment} task=${context.config.task}`);
  context.state.status = "searching";
  await baseline(context);
  const incompleteHoldout = holdoutRecord(context, "holdout_started");
  const completedHoldout = holdoutRecord(context, "holdout_completed");
  if (completedHoldout) {
    const promotionResult = completedHoldout.payload;
    const patchPath = applyWinner(context);
    const receipt = makeReceipt(context, promotionResult, patchPath);
    context.state.status = receipt.status;
    saveState(context);
    return receipt;
  }
  if (incompleteHoldout) {
    const previous = context.state.incumbent;
    applyRef(context.repo, "incumbent", context.state.baseline.commit);
    context.state.incumbent = { ...context.state.baseline };
    context.state.status = "retained";
    context.state.terminal_reason = "holdout_interrupted_closed";
    const promotionResult = {
      verdict: "retained",
      holdout_used: true,
      reason: "holdout_interrupted_closed",
      abandoned_candidate: previous.id,
    };
    append(context, "holdout_abandoned", promotionResult);
    const receipt = makeReceipt(context, promotionResult, null);
    saveState(context);
    return receipt;
  }
  const recovery = pendingRound(context);
  if (recovery) await runRound(context, Number(recovery.round), recovery);
  let reason = stopReason(context);
  while (!reason) {
    await runRound(context, context.state.round + 1);
    reason = stopReason(context);
  }
  context.state.terminal_reason = reason;
  append(context, "search_stopped", { reason, round: context.state.round, incumbent: context.state.incumbent.id });
  const promotionResult = await promotion(context);
  const patchPath = applyWinner(context);
  const receipt = makeReceipt(context, promotionResult, patchPath);
  context.state.status = receipt.status;
  saveState(context);
  progress(context.config, "DONE", `${receipt.status.toUpperCase()} baseline=${receipt.baseline.score.toFixed(6)} final=${receipt.incumbent.score.toFixed(6)}`);
  return receipt;
}

function summaryPayload(context, receipt = null) {
  return {
    schema: `${SCHEMA}.response`,
    ok: true,
    experiment: context.experiment,
    state: context.state.status,
    result: receipt,
    status: context.state,
    next_action: ["promoted", "retained"].includes(context.state.status)
      ? ["hill-climber", "inspect", context.experiment, "--json"]
      : ["hill-climber", "resume", context.experiment, "--json"],
  };
}

function emit(config, payload) {
  if (config.json) {
    process.stdout.write(`${JSON.stringify(payload)}\n`);
    return;
  }
  const result = payload.result;
  if (result) {
    process.stdout.write(`climb ${result.status}: ${result.experiment_id}\n`);
    process.stdout.write(`baseline ${result.baseline.score} -> final ${result.incumbent.score}\n`);
    process.stdout.write(`candidates ${result.counts.candidates} | kept ${result.counts.kept} | rejected ${result.counts.rejected} | invalid ${result.counts.invalid} | crashed ${result.counts.crashed}\n`);
    process.stdout.write(`tokens ${usageTotal(result.usage)} | wall ${result.wall_seconds}s | stop ${result.terminal_reason}\n`);
    process.stdout.write(`evidence ${payload.experiment}/receipt.json\n`);
    process.stdout.write(`report ${payload.experiment}/report.svg\n`);
    process.stdout.write(`applied ${result.applied ? "yes" : "no"}\n`);
    process.stdout.write(`next ${payload.next_action.join(" ")}\n`);
  } else {
    process.stdout.write(`climb ${payload.state}: ${payload.experiment}\n`);
    process.stdout.write(`next ${payload.next_action.join(" ")}\n`);
  }
}

function emitError(config, error, experiment = null) {
  const value = error instanceof ClimbError ? error : new ClimbError("E_INTERNAL", error.message ?? String(error));
  let nextAction = value.details?.next_action ?? null;
  if (!nextAction && experiment && ["E_EVALUATOR", "E_EVALUATOR_OUTPUT", "E_SETUP"].includes(value.code)) {
    nextAction = `fix the evaluator/setup command, then run hill-climber resume ${experiment}`;
  }
  if (!nextAction && experiment) nextAction = `hill-climber resume ${experiment}`;
  const payload = {
    schema: `${SCHEMA}.response`,
    ok: false,
    experiment,
    error: { code: value.code, message: bounded(value.message), details: value.details },
    next_action: nextAction,
  };
  if (config?.json) process.stdout.write(`${JSON.stringify(payload)}\n`);
  else {
    process.stderr.write(`BLOCKED ${safeLine(value.code)}: ${safeLine(value.message)}\n`);
    if (nextAction) process.stderr.write(`NEXT ${safeLine(nextAction)}\n`);
  }
  return value.exitCode;
}

function inspect(context, candidateId = null) {
  if (candidateId) {
    const directory = ensureInside(join(context.experiment, "candidates"),
      join(context.experiment, "candidates", candidateId), "candidate evidence");
    if (!existsSync(directory)) throw new ClimbError("E_NOT_FOUND", `candidate not found: ${candidateId}`);
    const names = ["generated.json", "result.json", "failure.json", "turn.json"].filter((name) => existsSync(join(directory, name)));
    return { schema: `${SCHEMA}.inspection`, experiment: context.experiment, candidate_id: candidateId,
      evidence: Object.fromEntries(names.map((name) => [name, readJson(join(directory, name))])) };
  }
  return summaryPayload(context, existsSync(join(context.experiment, "receipt.json")) ? readJson(join(context.experiment, "receipt.json")) : null);
}

async function main() {
  const request = await readStdin();
  validateConfig(request);
  if (["status", "inspect"].includes(request.action)) {
    let context;
    try { context = loadContext(request.experiment, request); }
    catch (error) { return emitError(request, error, request.experiment); }
    const payload = request.action === "inspect" ? inspect(context, request.candidate) : summaryPayload(context);
    emit(request, payload);
    return 0;
  }
  if (request.action === "stop") {
    let context;
    try { context = loadContext(request.experiment, request); }
    catch (error) { return emitError(request, error, request.experiment); }
    atomicWrite(join(context.experiment, "stop.request"), { requested_at: now(), requested_by: process.pid });
    if (existsSync(join(context.experiment, "run.lock"))) {
      try {
        const owner = readJson(join(context.experiment, "run.lock"));
        process.kill(owner.pid, "SIGINT");
      } catch {}
    }
    emit(request, summaryPayload(context));
    return 0;
  }
  let context;
  try {
    context = request.action === "run" ? createContext(request) : loadContext(request.experiment, request);
  } catch (error) {
    const experiment = request.action === "run"
      ? (existsSync(request.out) ? request.out : null)
      : request.experiment;
    return emitError(request, error, experiment);
  }
  const lock = new RunLock(join(context.experiment, "run.lock"));
  lock.acquire();
  const interrupt = () => context.abortController.abort("user interrupt");
  process.once("SIGINT", interrupt);
  process.once("SIGTERM", interrupt);
  try {
    if (request.action === "resume") {
      if (["promoted", "retained"].includes(context.state.status) && existsSync(join(context.experiment, "receipt.json"))) {
        emit(context.config, summaryPayload(context, readJson(join(context.experiment, "receipt.json"))));
        return 0;
      }
      append(context, "run_resumed", { previous_status: context.state.status });
    }
    const receipt = await execute(context);
    emit(context.config, summaryPayload(context, receipt));
    return receipt.status === "promoted" ? 0 : 1;
  } catch (error) {
    if (error instanceof InterruptedError || context.abortController.signal.aborted) {
      context.state.status = "interrupted";
      append(context, "run_interrupted", { reason: bounded(error.message ?? "interrupted") });
      progress(context.config, "INTERRUPTED",
        `experiment=${context.experiment} incumbent=${context.state.incumbent?.id ?? "none"} score=${context.state.incumbent?.score ?? "unknown"}`);
      return emitError(context.config, new InterruptedError(), context.experiment);
    }
    context.state.status = "failed";
    append(context, "run_failed", { code: error.code ?? "E_INTERNAL", message: bounded(error.message ?? String(error)) });
    return emitError(context.config, error, context.experiment);
  } finally {
    process.removeListener("SIGINT", interrupt);
    process.removeListener("SIGTERM", interrupt);
    lock.release();
  }
}

try {
  process.exitCode = await main();
} catch (error) {
  process.exitCode = emitError({}, error, null);
}
