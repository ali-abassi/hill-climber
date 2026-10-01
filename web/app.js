/* The workbench prepares commands and reads evidence. It never starts a model. */
"use strict";
const $ = (id) => document.getElementById(id);
let recipes = [];
let activeRecipe = null;
let prepared = null;
let nextCommand = "";
let planRevision = 0;
let resultsRequest = 0;
let inspectedExperiment = "";
let demoExperiment = "";
let chartData = null;
const numberFields = ["candidates", "rounds", "repeats", "holdoutRepeats", "minGain", "maxWallSeconds", "maxTokens", "generationParallel", "evaluationParallel"];
const icons = {
  code: "M5 5 1 9l4 4m8-8 4 4-4 4M11 2 7 16",
  performance: "M2 14a8 8 0 1 1 14 0M9 10l4-4M4 14h10",
  prompts: "M2 3h14v10H9l-4 3v-3H2zM5 6h8M5 9h5",
  writing: "m3 13-1 4 4-1L16 6l-3-3zM11 5l3 3",
  design: "M2 2h6v6H2zM11 2h5v6h-5zM2 11h6v5H2zM11 11h5v5h-5z",
  config: "M2 4h14M2 9h14M2 14h14M6 2v4M12 7v4M7 12v4",
};
function text(id, value) { $(id).textContent = value == null ? "" : String(value); }
function showError(id, message) { text(id, message); $(id).hidden = !message; }
function setBusy(id, busy, label) { const button = $(id); button.disabled = busy; if (label) button.textContent = label; }
async function api(path, body) {
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", headers: body === undefined ? {} : { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  let data;
  try { data = await response.json(); } catch { throw new Error("The local workbench returned an unreadable response. Check its terminal and try again."); }
  if (!response.ok || data.ok === false) throw new Error(data.error?.message || data.error || data.message || "The request could not be completed.");
  return data;
}
function showTab(name, focus = false) {
  document.querySelectorAll(".tab").forEach((tab) => { const selected = tab.dataset.tab === name; tab.classList.toggle("active", selected); if (selected) tab.setAttribute("aria-current", "page"); else tab.removeAttribute("aria-current"); });
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== `view-${name}`; });
  if (focus) { const title = $(`${name}-title`); title.setAttribute("tabindex", "-1"); title.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: "instant" }); }
  history.replaceState(null, "", `#${name}`);
  if (name === "results" && chartData && !$("result-content").hidden) drawChart(chartData.candidates, chartData.baseline);
}
function svgElement(tag, attributes = {}, value) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, entry] of Object.entries(attributes)) element.setAttribute(name, String(entry));
  if (value !== undefined) element.textContent = String(value);
  return element;
}
function renderRecipes() {
  $("recipe-picker").replaceChildren();
  for (const recipe of recipes) {
    const button = document.createElement("button"); button.type = "button"; button.className = "recipe-button"; button.dataset.recipe = recipe.id; button.setAttribute("aria-pressed", "false");
    const icon = svgElement("svg", { viewBox: "0 0 18 18", "aria-hidden": "true", class: "recipe-icon" });
    icon.append(svgElement("path", { d: icons[recipe.id] || icons.config, fill: "none", stroke: "currentColor", "stroke-width": "1.35", "stroke-linecap": "round", "stroke-linejoin": "round" }));
    const label = document.createElement("span"); label.textContent = recipe.name; button.append(icon, label);
    button.addEventListener("click", () => selectRecipe(recipe.id)); $("recipe-picker").append(button);
  }
}
function invalidatePlan() { planRevision += 1; prepared = null; $("command-panel").hidden = true; showError("plan-error", ""); }
function selectRecipe(id) {
  const recipe = recipes.find((entry) => entry.id === id); if (!recipe) return;
  if (activeRecipe?.id === id) return;
  const previous = activeRecipe; activeRecipe = recipe; invalidatePlan();
  document.querySelectorAll(".recipe-button").forEach((button) => { const selected = button.dataset.recipe === id; button.classList.toggle("selected", selected); button.setAttribute("aria-pressed", String(selected)); });
  $("task").placeholder = recipe.goal || "Describe the outcome you want.";
  text("goal-help", recipe.goalHint || "Name the result and what must stay true. Keep implementation choices open.");
  if (!$("mutable").value || $("mutable").value === (Array.isArray(previous?.mutable) ? previous.mutable.join("\n") : previous?.mutable)) $("mutable").value = Array.isArray(recipe.mutable) ? recipe.mutable.join("\n") : recipe.mutable || "";
  if (!$("details").value || $("details").value === previous?.details) $("details").value = recipe.details || "";
  let preservedCustom = false;
  for (const name of ["repeats", "holdoutRepeats", "minGain", "generationParallel", "evaluationParallel"]) {
    if (recipe[name] == null) continue;
    if (!previous || $(name).value === "" || Number($(name).value) === Number(previous[name])) $(name).value = recipe[name];
    else preservedCustom = true;
  }
  text("recipe-budget-advice", `Suggested repeats: ${recipe.repeats} development / ${recipe.holdoutRepeats} holdout. ${preservedCustom ? "Your custom budget values were kept; review them for this kind of work." : "Measure baseline noise before choosing a minimum gain."}`);
  text("recipe-title", recipe.name); text("recipe-description", recipe.description); text("recipe-score", recipe.score); text("recipe-feedback", recipe.feedback);
  text("mobile-recipe-description", recipe.description);
  const gates = Array.isArray(recipe.gates) ? recipe.gates : String(recipe.gates || "").split(/;\s*/).filter(Boolean);
  $("recipe-gates").replaceChildren(); for (const gate of gates) { const li = document.createElement("li"); li.textContent = gate; $("recipe-gates").append(li); }
  $("guide-gates").replaceChildren(); for (const gate of gates) { const li = document.createElement("li"); li.textContent = gate; $("guide-gates").append(li); }
  text("eval-help", recipe.evalHint || "A fixed evaluator measures quality. A private holdout checks that the gain lasts.");
  text("guide-recipe-name", recipe.name.toLowerCase()); text("guide-goal", recipe.goal); text("guide-score", recipe.score); text("guide-mutable", `Example mutable surface: ${Array.isArray(recipe.mutable) ? recipe.mutable.join(", ") : recipe.mutable}`);
  text("guide-repeats", Number(recipe.repeats) > 1 ? "This measure can vary between runs. Repeat development and holdout grading at least three times, measure the baseline spread, and set a minimum gain above that noise floor. Keep timing evaluators serial." : "For deterministic checks, one repeat is a reasonable starting point. For model judgments or any variable measure, use repeated grading and a minimum gain above the baseline noise floor.");
  text("guide-feedback", `Actionable development feedback: ${recipe.feedback || "Explain the observed gap and affected cases."}`);
  updateBudget();
}
function updateBudget() { const candidates = Number($("candidates").value); const rounds = Number($("rounds").value); text("budget-summary", `${candidates || "—"} ${candidates === 1 ? "route" : "routes"} · ${rounds || "—"} ${rounds === 1 ? "round" : "rounds"}`); }
function formValues() {
  const values = Object.fromEntries(new FormData($("plan-form"))); values.recipe = activeRecipe?.id;
  for (const name of numberFields) values[name] = Number(values[name]); return values;
}
async function copy(value, button) {
  const original = button.textContent;
  try { await navigator.clipboard.writeText(value); button.textContent = "Copied ✓"; setTimeout(() => { button.textContent = original; }, 1800); }
  catch { button.textContent = "Select and copy below"; setTimeout(() => { button.textContent = original; }, 2200); }
}
function score(value) { return typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 5 }).format(value) : "—"; }
function quoteArgument(value) { return `'${String(value).replaceAll("'", "'\\''")}'`; }
function commandFromAction(action) { return Array.isArray(action) ? action.map(quoteArgument).join(" ") : ""; }
function drawChart(candidates, baseline) {
  chartData = { candidates, baseline };
  const chart = $("chart"); chart.replaceChildren();
  if (!chart.clientWidth) return;
  const points = candidates.filter((candidate) => typeof candidate.score === "number" && Number.isFinite(candidate.score) && Number.isFinite(Number(candidate.round)));
  if (!points.length || !Number.isFinite(baseline)) { const empty = document.createElement("p"); empty.className = "chart-empty"; empty.textContent = "Score history appears when verified evaluations are available."; chart.append(empty); text("chart-caption", "No scores are inferred from candidate descriptions."); return; }
  const width = Math.max(300, chart.clientWidth); const height = 235; const left = 45; const top = 15; const bottom = 198; const right = width - 28; const rounds = Math.max(1, ...points.map((point) => Number(point.round)));
  const allScores = [baseline, ...points.map((point) => point.score)]; let low = Math.min(...allScores); let high = Math.max(...allScores); const span = high - low || Math.max(1, Math.abs(high) * .15); low -= span * .15; high += span * .15;
  const x = (round) => left + (right - left) * round / rounds; const y = (value) => bottom - (value - low) / (high - low) * (bottom - top);
  const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `Verified development scores across ${rounds} rounds. Baseline ${score(baseline)}.` });
  for (let i = 0; i < 4; i++) { const value = low + (high - low) * i / 3; const position = y(value); svg.append(svgElement("line", { x1: left, x2: right, y1: position, y2: position, stroke: "#e5e9e0", "stroke-width": 1 })); svg.append(svgElement("text", { x: left - 10, y: position + 4, fill: "#657067", "font-size": 10, "text-anchor": "end", "font-family": "system-ui" }, score(value))); }
  let incumbent = baseline; let line = `M ${x(0)} ${y(baseline)}`;
  for (let round = 1; round <= rounds; round++) { const selected = points.filter((point) => Number(point.round) === round && ["kept", "selected", "promoted"].includes(point.verdict)); line += ` H ${x(round)}`; for (const point of selected) incumbent = point.score; line += ` V ${y(incumbent)}`; }
  svg.append(svgElement("path", { d: line, fill: "none", stroke: "#275d3b", "stroke-width": 2.5, "stroke-linejoin": "round" }));
  for (const point of points) { const kept = ["kept", "selected", "promoted"].includes(point.verdict); const circle = svgElement("circle", { cx: x(Number(point.round)), cy: y(point.score), r: kept ? 5 : 4, fill: kept ? "#275d3b" : "#d1dbcb", stroke: "#fff", "stroke-width": 1.5 }); circle.append(svgElement("title", {}, `${point.id}: ${score(point.score)} · ${point.verdict || point.status || "evaluated"}`)); svg.append(circle); }
  svg.append(svgElement("circle", { cx: x(0), cy: y(baseline), r: 5, fill: "#275d3b", stroke: "#fff", "stroke-width": 1.5 }));
  for (let round = 0; round <= rounds; round++) { if (rounds > 12 && round !== 0 && round !== rounds && round % Math.ceil(rounds / 10)) continue; svg.append(svgElement("text", { x: x(round), y: 222, fill: "#657067", "font-size": 11, "font-family": "system-ui", "text-anchor": "middle" }, round === 0 ? "Baseline" : `Round ${round}`)); }
  chart.append(svg); text("chart-caption", "Each dot is a measured candidate. The green path follows selected development incumbents; final promotion is a separate private check.");
}
function renderCandidates(candidates) {
  const target = $("candidate-table"); target.replaceChildren();
  if (!candidates.length) { const empty = document.createElement("p"); empty.className = "field-help"; empty.textContent = "No candidate decisions have been recorded yet."; target.append(empty); return; }
  const table = document.createElement("table"); const head = document.createElement("thead"); const row = document.createElement("tr"); for (const label of ["Candidate", "Score", "Decision", "Evidence"]) { const th = document.createElement("th"); th.scope = "col"; th.textContent = label; row.append(th); } head.append(row); table.append(head);
  const body = document.createElement("tbody");
  for (const candidate of candidates) {
    const tr = document.createElement("tr");
    for (const value of [candidate.id, score(candidate.score), candidate.verdict || candidate.status || "Pending"]) { const td = document.createElement("td"); td.textContent = value; tr.append(td); }
    const evidence = document.createElement("td"); const details = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = candidate.reason || candidate.mechanism || "View details"; details.append(summary);
    const feedback = Array.isArray(candidate.feedback) ? candidate.feedback.join("\n") : candidate.feedback;
    for (const [label, value] of [["Mechanism", candidate.mechanism], ["Hypothesis", candidate.hypothesis], ["Development feedback", feedback], ["Gates", candidate.gates]]) {
      if (value == null || value === "") continue;
      const paragraph = document.createElement("p"); const heading = document.createElement("strong"); heading.textContent = `${label}: `; paragraph.append(heading, document.createTextNode(typeof value === "object" ? JSON.stringify(value) : String(value))); details.append(paragraph);
    }
    evidence.append(details); tr.append(evidence); body.append(tr);
  }
  table.append(body); target.append(table);
}
function renderResults(data) {
  if (data.verified !== true || data.inspect?.ok !== true) throw new Error("The controller could not verify this experiment. Its scores will not be displayed.");
  const response = data.inspect; const state = response.status || {}; const receipt = response.result || {}; const candidates = Array.isArray(data.candidates) ? data.candidates : [];
  inspectedExperiment = response.experiment || "";
  if (data.demo) demoExperiment = inspectedExperiment;
  if (inspectedExperiment === demoExperiment && demoExperiment) data.demo = true;
  const verdict = receipt.status || response.state || state.status || "in progress";
  const baseline = receipt.baseline?.score ?? state.baseline?.score; const final = receipt.incumbent?.score ?? state.incumbent?.score;
  const count = receipt.counts?.candidates ?? state.counts?.candidates ?? candidates.length;
  text("result-source", data.demo ? "Deterministic demo · no model calls" : "Controller-verified experiment");
  text("result-directory", `Verified directory: ${inspectedExperiment}`);
  text("result-task", receipt.task || state.task || (data.demo ? "A small, measured demonstration" : response.experiment));
  text("result-verdict", verdict); $("result-verdict").classList.toggle("retained", verdict === "retained");
  const holdoutIndependent = receipt.promotion?.holdout_independent;
  let explanation = verdict === "promoted" ? "The selected gain passed final promotion. Inspect its patch and receipt before applying." : verdict === "retained" ? "The baseline was retained. A development gain did not earn final promotion, or no eligible gain was found." : "This experiment has not produced a final promotion decision. Development scores are provisional.";
  if (holdoutIndependent === false) explanation += " This run reused the development evaluator for promotion; it does not establish an independent holdout gain.";
  text("result-explanation", explanation); text("stat-baseline", score(baseline)); text("stat-final", score(final)); text("stat-candidates", count); text("stat-applied", receipt.applied === true || state.applied === true ? "Yes" : "No");
  $("results-empty").hidden = true; $("result-content").hidden = false;
  drawChart(candidates, baseline); renderCandidates(candidates);
  const usage = receipt.usage || state.usage || {}; const totalTokens = Number(usage.input_tokens || 0) + Number(usage.output_tokens || 0);
  const evidence = [["Development best", score(data.developmentBest)], ["Holdout", receipt.promotion?.verdict || "Not complete"], ["Stop reason", receipt.terminal_reason || state.terminal_reason || "Not complete"], ["Wall time", Number.isFinite(receipt.wall_seconds) ? `${score(receipt.wall_seconds)} s` : "Not complete"], ["Tokens", totalTokens ? score(totalTokens) : "Not reported"], ["Patch", receipt.patch?.path || "Not available"], ["Directory", response.experiment || "—"]];
  $("evidence-details").replaceChildren(); for (const [name, value] of evidence) { const dt = document.createElement("dt"); dt.textContent = name; const dd = document.createElement("dd"); dd.textContent = value; $("evidence-details").append(dt, dd); }
  nextCommand = commandFromAction(response.next_action); text("next-command", nextCommand); $("copy-next").hidden = !nextCommand;
  text("raw-response", JSON.stringify(data, null, 2)); $("results-empty").hidden = true; $("result-content").hidden = false;
}
document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => showTab(button.dataset.tab)));
window.addEventListener("hashchange", () => { const name = location.hash.slice(1); showTab(["plan", "results", "guide"].includes(name) ? name : "plan"); });
window.addEventListener("resize", () => { if (chartData && !$("view-results").hidden) drawChart(chartData.candidates, chartData.baseline); });
$("open-guide").addEventListener("click", () => showTab("guide", true)); $("guide-to-plan").addEventListener("click", () => showTab("plan", true));
$("mobile-open-guide").addEventListener("click", () => showTab("guide", true));
$("show-contract").addEventListener("click", () => { showTab("guide"); $("evaluator-contract").scrollIntoView({ block: "start", behavior: "instant" }); });
$("plan-form").addEventListener("input", () => { invalidatePlan(); updateBudget(); });
$("plan-form").addEventListener("change", invalidatePlan);
$("plan-form").addEventListener("submit", async (event) => { event.preventDefault(); invalidatePlan(); const revision = planRevision; setBusy("prepare-button", true, "Preparing…"); try {
  const data = await api("/api/plan", formValues()); if (revision !== planRevision) return; if (typeof data.command !== "string" || typeof data.brief !== "string") throw new Error("The plan response is incomplete. Check the local server."); prepared = data;
  text("launch-command", data.command); text("attempt-description", `At most ${data.maxAttempts ?? Number($("candidates").value) * Number($("rounds").value)} candidate attempts, plus baseline and final grading. Model usage starts only when you run the command.`);
  $("plan-warnings").replaceChildren(); for (const warning of data.warnings || []) { const li = document.createElement("li"); li.textContent = warning; $("plan-warnings").append(li); } $("plan-warnings").hidden = !(data.warnings || []).length;
  $("command-panel").hidden = false; $("experiment").value = $("out").value; $("command-panel").scrollIntoView({ block: "start", behavior: "instant" });
} catch (error) { if (revision === planRevision) showError("plan-error", error.message); } finally { setBusy("prepare-button", false, "Prepare climb ↗"); } });
$("copy-command").addEventListener("click", () => { if (prepared) copy(prepared.command, $("copy-command")); });
$("copy-next").addEventListener("click", () => copy(nextCommand, $("copy-next")));
$("download-brief").addEventListener("click", () => { if (!prepared) return; const url = URL.createObjectURL(new Blob([prepared.brief], { type: "text/markdown;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = "hill-climber-task.md"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
$("experiment").addEventListener("input", () => { resultsRequest += 1; $("result-content").hidden = true; $("results-empty").hidden = false; showError("inspect-error", ""); });
$("inspect-form").addEventListener("submit", async (event) => { event.preventDefault(); const request = ++resultsRequest; showError("inspect-error", ""); $("result-content").hidden = true; $("results-empty").hidden = true; setBusy("inspect-button", true, "Verifying…"); try { const data = await api("/api/inspect", { experiment: $("experiment").value.trim() }); if (request === resultsRequest) renderResults(data); } catch (error) { if (request === resultsRequest) { showError("inspect-error", error.message); $("results-empty").hidden = false; } } finally { setBusy("inspect-button", false, "Inspect"); } });
$("load-demo").addEventListener("click", async () => { const request = ++resultsRequest; showError("inspect-error", ""); $("result-content").hidden = true; $("results-empty").hidden = true; setBusy("load-demo", true, "Building demo…"); try { const data = await api("/api/demo", {}); if (request === resultsRequest) renderResults(data); } catch (error) { if (request === resultsRequest) { showError("inspect-error", error.message); $("results-empty").hidden = false; } } finally { setBusy("load-demo", false, "Explore a demo ↗"); } });
$("refresh-result").addEventListener("click", async () => { if (!inspectedExperiment) return; const request = ++resultsRequest; showError("inspect-error", ""); $("result-content").hidden = true; setBusy("refresh-result", true, "Verifying…"); try { const data = await api("/api/inspect", { experiment: inspectedExperiment }); if (request === resultsRequest) renderResults(data); } catch (error) { if (request === resultsRequest) { showError("inspect-error", error.message); $("results-empty").hidden = false; } } finally { setBusy("refresh-result", false, "Refresh"); } });
async function initialize() { try { const data = await api("/api/recipes"); recipes = data.recipes || []; if (!recipes.length) throw new Error("No task recipes were found. Check the local workbench server."); renderRecipes(); selectRecipe(recipes[0].id); } catch (error) { showError("plan-error", error.message); text("recipe-title", "Recipes unavailable"); $("prepare-button").disabled = true; } const initial = location.hash.slice(1); showTab(["plan", "results", "guide"].includes(initial) ? initial : "plan"); }
initialize();
