import {
  businessKnowledgeReady,
  canAccessModule,
  canAccessObjectiveView,
  demoData,
  getIntegration,
  integrations,
  moduleNavStatus,
  modules,
  selectStrategy,
  strategies,
} from "./demo-data.js";
import { createApiClient, tableViewModels, taskContractFrom } from "./api-client.js";
import {
  beginSimulation,
  completeSimulation,
  createObjective,
  createWorkspaceState,
  getActiveObjective,
  loadWorkspaceState,
  saveWorkspaceState,
  selectObjective,
  workspaceProgress,
} from "./workspace-state.js";
import {
  inferenceWaitingMarkup,
  minimumInferenceWait,
  simulationWaitingMarkup,
  startWaitingAnimations,
} from "./waiting-animations.js";

const app = document.querySelector("#app");
const api = createApiClient();
const params = new URLSearchParams(window.location.search);
const legacyModules = {
  import: "data",
  connect: "data",
  context: "knowledge",
  objective: "objectives",
  model: "objectives",
  strategy: "objectives",
  learn: "experiments",
};
const requestedPage = params.get("module") || legacyModules[params.get("stage")] || null;
const embeddedObjectiveView = { insights: "insights", decisions: "decisions" }[requestedPage];
const requestedModule = embeddedObjectiveView ? "objectives" : requestedPage;
const state = loadWorkspaceState(window.localStorage) ?? createWorkspaceState();
let stopWaitingAnimations = () => {};
if (requestedModule && modules.some((item) => item.id === requestedModule)) state.module = requestedModule;
if (embeddedObjectiveView || params.get("view")) state.objectiveView = embeddedObjectiveView || params.get("view");

const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "'": "&#39;",
  '"': "&quot;",
})[character]);

const icon = (name) => {
  const paths = {
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    database: '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    lock: '<rect x="6" y="10" width="12" height="10" rx="2"/><path d="M9 10V7a3 3 0 0 1 6 0v3"/>',
    book: '<path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4Z"/><path d="M8 16h10"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m14 10 6-6"/>',
    people: '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 5v1"/>',
    spark: '<path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z"/>',
    flask: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 15h8"/>',
    warning: '<path d="M12 4 3 20h18L12 4Z"/><path d="M12 10v4M12 17h.01"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
  };
  return `<svg aria-hidden="true" viewBox="0 0 24 24">${paths[name]}</svg>`;
};

const moduleIcons = {
  data: "database",
  knowledge: "book",
  objectives: "target",
  experiments: "flask",
};

const moduleTitles = {
  data: ["Data connections", "Give StructAgent a trustworthy view of your business."],
  knowledge: ["Business knowledge", "Define what success means before asking the system to optimise it."],
  objectives: ["Objectives", "Each objective carries its own business brief, model evidence and decision work."],
  experiments: ["Experiments", "Monitor a portfolio of controlled tests and bank what the business learns."],
};

function progress() {
  return workspaceProgress(state);
}

function navStatusMarkup(moduleId) {
  const status = moduleNavStatus(moduleId, progress());
  if (status.kind === "complete") return `<i class="nav-check" aria-label="Complete">${icon("check")}</i>`;
  if (status.kind === "none") return "";
  return `<i class="nav-badge ${status.kind}">${status.label}</i>`;
}

function setQuery() {
  const view = state.module === "objectives" && state.objectiveView !== "brief" ? `&view=${state.objectiveView}` : "";
  window.history.replaceState({}, "", `${window.location.pathname}?module=${state.module}${view}`);
}

function fixtureBadge() {
  return `<div class="fixture-badge"><span>FR</span><p><b>Fashion retail</b><small>Demo workspace</small></p></div>`;
}

function sidebar() {
  const groups = [...new Set(modules.map((item) => item.group))];
  return `<aside class="sidebar">
    <div class="workspace"><span>BK</span><p><small>Workspace</small><b>Birch &amp; Kite</b><i>Decision OS</i></p></div>
    <nav class="module-nav" aria-label="Workspace modules">
      ${groups.map((group) => `<section><h2>${group}</h2>${modules.filter((item) => item.group === group).map((item) => {
        const accessible = canAccessModule(item.id, progress());
        return `<button data-module="${item.id}" ${accessible ? "" : "disabled"} class="${state.module === item.id ? "active" : ""}">
          <span>${icon(accessible ? moduleIcons[item.id] : "lock")}</span><p><b>${item.label}</b><small>${accessible ? item.hint : lockedReason(item.id)}</small></p>${navStatusMarkup(item.id)}
        </button>`;
      }).join("")}</section>`).join("")}
    </nav>
    <div class="system-note"><span></span><p><b>Evidence thread active</b><small>Recommendations stay linked to their source.</small></p></div>
  </aside>`;
}

function lockedReason(moduleId) {
  if (moduleId === "knowledge") return "Connect data to unlock";
  if (moduleId === "objectives") return "Define success to unlock";
  return "Stage an intervention first";
}

function shell() {
  const [title, description] = moduleTitles[state.module];
  return `<div class="app-shell">
    <header class="topbar"><a class="brand"><span class="brand-glyph"></span><b>StructAgent</b></a>${fixtureBadge()}<div class="owner"><span>BK</span><p><b>Bethany King</b><small>Owner</small></p></div></header>
    <div class="app-body">${sidebar()}<main class="main"><header class="module-header"><div><span>${modules.find((item) => item.id === state.module)?.group}</span><h1>${title}</h1><p>${description}</p></div></header>${moduleContent()}</main></div>
  </div>`;
}

function integrationChooser() {
  const selected = getIntegration(state.source);
  const connectionLabel = state.apiStatus === "loading" ? "Loading contract…" : `Connect ${selected.name} ${icon("arrow")}`;
  return `<section class="integration-layout">
    <div class="section-intro"><span class="eyebrow">Connect a source</span><h2>Where does your business data live?</h2><p>Choose an integration to load the fashion retail demo dataset. No credentials are requested.</p></div>
    <div class="source-grid" aria-label="Database integrations">${integrations.map((source) => `<button data-source="${source.id}" class="source-card ${state.source === source.id ? "selected" : ""}"><span>${source.mark}</span><p><b>${source.name}</b><small>${source.detail}</small></p><i>${state.source === source.id ? icon("check") : "Choose"}</i></button>`).join("")}</div>
    <div class="connection-panel"><header><span>${selected.mark}</span><p><small>Selected integration</small><b>${selected.name}</b></p><i>Demo connection</i></header>
      <div class="mock-fields"><p><small>Host</small><b>fashion-demo.sql.local</b></p><p><small>Database</small><b>retail_warehouse</b></p><p><small>Schema</small><b>public</b></p><p><small>Access</small><b>Read-only</b></p></div>
      <footer><p><b>No credentials are used.</b><small>Continuing loads reviewed schema metadata from the local API.</small></p><button data-connect ${state.apiStatus === "loading" ? "disabled" : ""}>${connectionLabel}</button></footer>
    </div>
    ${state.apiError ? `<div class="api-error">${icon("warning")}<p><b>Local API unavailable</b><small>${escapeHtml(state.apiError)} Start the API, then try again.</small></p></div>` : ""}
    <div class="security-note">${icon("lock")}<p><b>Read-only access</b><small>The demo displays schema access without collecting or storing warehouse credentials.</small></p></div>
  </section>`;
}

function tableExplorer() {
  const tables = state.dataset ? tableViewModels(state.dataset, demoData.rowLabels) : demoData.tables.map((table) => ({ ...table, detail: table.note }));
  const relationshipCount = state.dataset?.tables.flatMap((table) => table.columns).filter((column) => column.foreign_key).length ?? 2;
  return `<div class="table-explorer"><div class="table-list">${tables.map((table) => `<button data-table="${table.name}" class="${state.table === table.name ? "active" : ""}"><span>${icon("database")}</span><p><b>${table.name}</b><small>${table.rows} rows · ${table.detail}</small></p></button>`).join("")}</div>
    <div class="relation-canvas"><svg viewBox="0 0 640 300" preserveAspectRatio="none" aria-hidden="true"><path d="M130 80 C260 80 220 150 320 150"/><path d="M320 150 C410 150 430 65 525 65"/></svg>
      <button class="node node-a ${state.table === "customer" ? "active" : ""}" data-table="customer"><small>identity</small><b>customer</b><span>customer_id</span></button>
      <button class="node node-b ${state.table === "transactions" ? "active" : ""}" data-table="transactions"><small>event</small><b>transactions</b><span>t_dat</span></button>
      <button class="node node-c ${state.table === "article" ? "active" : ""}" data-table="article"><small>entity</small><b>article</b><span>article_id</span></button>
      <div class="canvas-status"><span></span><p><b>Contract verified</b><small>${relationshipCount} relationships · V1 metadata</small></p></div>
    </div></div>`;
}

function dataModule() {
  if (!state.connected) return integrationChooser();
  return `<section class="data-module"><div class="section-intro with-action"><div><span class="eyebrow">Connected data</span><h2>Your fashion retail data has a shape.</h2><p>The API returned three related tables that support customer classification and article-sales regression tasks.</p></div><button class="secondary" data-disconnect>Change integration</button></div>
    <div class="connection-ready"><span></span><p><small>${getIntegration(state.source).name} · read-only</small><b>${demoData.short}</b></p><i>${icon("check")} Connected</i></div>
    ${tableExplorer()}
    <div class="data-receipt"><p><small>Contract</small><b>V1</b></p><p><small>Relationships</small><b>2 verified</b></p><p><small>Available task</small><b>7-day sales</b></p><button data-open-knowledge>Open business knowledge ${icon("arrow")}</button></div>
  </section>`;
}

function knowledgeModule() {
  const metricOptions = ["Item sales", "Gross margin", "Stock availability", "Sell-through rate"];
  const guardrails = [
    ["margin", "Gross margin", "Do not reduce"],
    ["stockouts", "Stock-out exposure", "Keep below 5%"],
    ["discount", "Discount exposure", "No blanket markdowns"],
  ];
  return `<section class="knowledge-layout"><div class="section-intro"><span class="eyebrow">Knowledge centre</span><h2>The system needs your definition of a good decision.</h2><p>Connected data describes what happened. Business knowledge tells StructAgent which outcomes matter and which trade-offs are unacceptable.</p></div>
    <div class="knowledge-card business-context"><label for="business-context">How the business works</label><textarea id="business-context">We are a growing fashion retailer. We need a seven-day view of article demand so merchandising actions improve sales without creating stock-outs or margin pressure.</textarea><small>Plain language is useful. This stays editable.</small></div>
    <div class="knowledge-card"><div class="panel-heading"><span>Primary success metric</span><small>Choose one</small></div><div class="metric-grid">${metricOptions.map((metric) => `<button data-metric="${metric}" class="choice ${state.metric === metric ? "selected" : ""}"><span></span><p><b>${metric}</b><small>${state.metric === metric ? "Current focus" : "Select"}</small></p></button>`).join("")}</div></div>
    <div class="knowledge-card"><div class="panel-heading"><span>Decision guardrails</span><small>Select all that apply</small></div><div class="guardrail-list">${guardrails.map(([id, label, detail]) => `<button data-guardrail="${id}" class="guardrail ${state.guardrails.includes(id) ? "selected" : ""}"><span>${state.guardrails.includes(id) ? icon("check") : ""}</span><p><b>${label}</b><small>${detail}</small></p></button>`).join("")}</div></div>
    <div class="knowledge-summary"><span>Business knowledge</span><p>Improve <b>${state.metric}</b> while respecting <b>${state.guardrails.length} guardrails</b>.</p><button data-save-knowledge ${businessKnowledgeReady(state.metric, state.guardrails) ? "" : "disabled"}>${state.guardrails.length ? (state.knowledgeComplete ? "Update and open objectives" : "Save and open objectives") : "Select at least one guardrail"} ${icon("arrow")}</button></div>
  </section>`;
}

function objectiveReference(objective) {
  return `${objective.confirmed ? "OBJ" : "DRAFT"}-${String(objective.number).padStart(2, "0")}`;
}

function objectiveNavigation(objective) {
  const views = [
    ["brief", "Objective brief", objective.confirmed ? "Defined" : "Draft"],
    ["insights", "Item insights", objective.confirmed ? `Evidence run ${objective.rtjRun}` : "Run inference first"],
    ["decisions", "Decision Studio", objective.confirmed ? `Uses evidence run ${objective.rtjRun}` : "Waiting for evidence"],
  ];
  return `<nav class="objective-nav" aria-label="Selected objective sections">${views.map(([id, label, status]) => {
    const accessible = canAccessObjectiveView(id, objective);
    return `<button data-objective-view="${id}" ${accessible ? "" : "disabled"} class="${state.objectiveView === id ? "active" : ""}"><span>${icon(id === "brief" ? "target" : id === "insights" ? "people" : "spark")}</span><p><b>${label}</b><small>${status}</small></p></button>`;
  }).join("")}</nav>`;
}

function objectivesModule() {
  const objective = getActiveObjective(state) ?? createObjective(state);
  if (!canAccessObjectiveView(state.objectiveView, objective)) state.objectiveView = "brief";
  const content = {
    brief: objectiveBrief,
    insights: insightsModule,
    decisions: decisionsModule,
  }[state.objectiveView](objective);
  const picker = state.objectives.map((item) => `<button data-select-objective="${item.id}" class="${item.id === objective.id ? "active" : ""}"><span>${item.confirmed ? "OBJ" : "DRAFT"}-${String(item.number).padStart(2, "0")}</span><b>${escapeHtml(item.title)}</b></button>`).join("");
  return `<section class="objective-workspace"><div class="portfolio-bar"><div><span class="eyebrow">Objective portfolio</span><p><b>${state.objectives.length} active objective${state.objectives.length === 1 ? "" : "s"}</b><small>Insights and decisions stay attached to the objective that created them.</small></p></div><div class="objective-picker">${picker}</div><button class="secondary" data-new-objective>${icon("plus")} Add objective</button></div><div class="objective-container"><header class="objective-context"><div><span>${objectiveReference(objective)}</span><p><small>${objective.confirmed ? "Selected objective" : "New objective"}</small><b>${escapeHtml(objective.title)}</b></p></div>${objectiveNavigation(objective)}</header>${content}</div></section>`;
}

function objectiveBrief(objective) {
  return `<div class="objective-chat chat-only"><header><span>S</span><p><b>Objective partner</b><small>Uses your business knowledge and connected schema</small></p><i>${objective.confirmed ? "Objective ready" : "Defining objective"}</i></header>
    <div class="chat-thread objective-thread"><div class="chat agent"><p>What business outcome should we improve first?</p><small>I’ll check the available data, sharpen the objective, and prepare the inference task with you.</small></div>
      ${objective.fit ? `<div class="chat human"><p>${escapeHtml(objective.title)}</p></div>${objectiveAgentGuidance(objective)}` : ""}
    </div>
    <div class="objective-prompts"><span>Suggested starts</span><button data-objective-fit="supported"><b>Forecast seven-day item sales</b><small>Supported by current data</small></button><button data-objective-fit="unsupported"><b>Increase store footfall</b><small>Needs additional data</small></button></div>
    <form class="objective-compose"><label for="objective-input">Describe the objective in your own words</label><div><input id="objective-input" value="${escapeHtml(objective.title === "Define a business outcome" ? "Forecast sales revenue for each article over the next seven days" : objective.title)}"><button>${icon("arrow")}</button></div></form>
  </div>`;
}

function selectedDefaultTask(objective) {
  const tasks = state.defaultTaskCatalog?.tasks ?? [];
  return tasks.find((task) => task.task_id === objective.selectedTaskId) ?? tasks[0] ?? null;
}

function defaultTaskSelector(objective) {
  const tasks = state.defaultTaskCatalog?.tasks ?? [];
  if (!tasks.length) {
    return `<div class="api-error">${icon("warning")}<p><b>Task catalog unavailable</b><small>Reconnect the demo dataset to load the reviewed defaults.</small></p></div>`;
  }
  return `<div class="default-task-selector"><small>Choose reviewed task</small><div>${tasks.map((task) => `<button data-default-task="${escapeHtml(task.task_id)}" class="${task.task_id === objective.selectedTaskId ? "selected" : ""}"><span>${task.task_type === "regression" ? "REG" : "CLS"}</span><p><b>${escapeHtml(task.display_name)}</b><small>${escapeHtml(task.description)}</small></p><i>${task.horizon.value} ${escapeHtml(task.horizon.unit)}</i></button>`).join("")}</div></div>`;
}

function materializationReceipt(objective) {
  const result = objective.materialization?.tasks?.[0];
  if (!result) return "";
  return `<div class="materialization-receipt"><header>${icon("check")}<p><small>Synthetic Daytona execution</small><b>${escapeHtml(objective.materialization.execution_id)}</b></p><i>Sandbox deleted</i></header><div><p><small>Package digest</small><b>${escapeHtml(result.package_sha256.slice(0, 16))}…</b></p><p><small>Train rows</small><b>${result.train_rows}</b></p><p><small>Validation rows</small><b>${result.validation_rows}</b></p><p><small>Masked test rows</small><b>${result.test_rows}</b></p></div><footer>Private sandbox · network blocked · SQL canary passed · artifacts verified</footer></div>`;
}

function objectiveAgentGuidance(objective) {
  if (objective.fit === "unsupported") {
    return `<div class="chat agent agent-task data-gap"><div class="agent-task-status"><span>${icon("warning")}</span><p><small>Data check</small><b>We need one more source before creating this task.</b></p></div><p>Purchases cannot show who entered a store without buying. I’ve paused this objective so the resulting model does not create false confidence.</p><div class="missing-data"><b>Data to collect</b><span>store_id</span><span>visit_timestamp</span><span>customer_id or cohort</span></div>${objective.collectionPlan ? `<div class="plan-ready">${icon("check")}<p><b>Collection plan created</b><small>Add store-visit events, validate identity coverage, then return to this conversation.</small></p></div>` : `<button class="agent-action" data-collection-plan>Create data collection plan ${icon("arrow")}</button>`}</div>`;
  }
  const task = selectedDefaultTask(objective);
  if (objective.materializationStatus === "loading") {
    return `<div class="chat agent agent-task"><div class="agent-task-status"><span class="status-spinner"></span><p><small>Daytona sandbox running</small><b>Materializing ${escapeHtml(task?.display_name ?? "the reviewed task")}.</b></p></div><p>The trusted API is creating a private synthetic sandbox, validating the task package, and deleting the sandbox before returning.</p></div>`;
  }
  if (objective.materializationError) {
    return `<div class="chat agent agent-task data-gap"><div class="agent-task-status"><span>${icon("warning")}</span><p><small>Daytona execution</small><b>The synthetic task was not materialized.</b></p></div><p>${escapeHtml(objective.materializationError)}</p>${defaultTaskSelector(objective)}<button class="agent-action" data-launch-daytona>Try Daytona again ${icon("arrow")}</button></div>`;
  }
  if (objective.apiStatus === "loading") {
    return inferenceWaitingMarkup();
  }
  if (objective.apiError) {
    return `<div class="chat agent agent-task data-gap"><div class="agent-task-status"><span>${icon("warning")}</span><p><small>Fixture API</small><b>The synthetic evaluation preview is unavailable.</b></p></div><p>${escapeHtml(objective.apiError)}</p><button class="agent-action" data-run-fixture>Try the fixture preview again ${icon("arrow")}</button></div>`;
  }
  if (objective.confirmed) {
    const contract = taskContractFrom(objective.taskDraft);
    return `<div class="chat agent agent-task"><div class="agent-task-status"><span>${icon("check")}</span><p><small>Objective ready</small><b>The V1 task contract is defined and linked to this objective.</b></p></div><div class="task-preview"><p><small>Entity</small><b>${escapeHtml(contract.entity.table)}</b></p><p><small>Outcome window</small><b>${contract.horizon.value} ${contract.horizon.unit}</b></p><p><small>Task</small><b>Sales regression</b></p></div><button class="agent-action" data-objective-view="insights">Open item insights ${icon("arrow")}</button></div>`;
  }
  if (objective.materialization) {
    const fixturePreview = objective.selectedTaskId === "rel-hm/item-sales" ? `<button class="agent-action" data-run-fixture>Continue to synthetic evaluation preview ${icon("arrow")}</button>` : `<div class="fixture-separation"><b>Materialization complete.</b><span>No churn evaluation result is available in the current fixture demo.</span></div>`;
    return `<div class="chat agent agent-task"><div class="agent-task-status"><span>${icon("check")}</span><p><small>Task package verified</small><b>${escapeHtml(task?.display_name ?? objective.selectedTaskId)} completed in Daytona.</b></p></div>${materializationReceipt(objective)}${fixturePreview}</div>`;
  }
  return `<div class="chat agent agent-task"><div class="agent-task-status"><span>${icon("check")}</span><p><small>Supported by current data</small><b>Two reviewed H&amp;M defaults are executable.</b></p></div><p>Select a task. Clicking launch explicitly approves a synthetic, bounded Daytona materialization; it does not transfer private H&amp;M data or run model training.</p>${defaultTaskSelector(objective)}<button class="agent-action" data-launch-daytona ${task ? "" : "disabled"}>Launch ${escapeHtml(task?.display_name ?? "task")} in Daytona ${icon("arrow")}</button></div>`;
}

function insightsModule(objective) {
  const evaluation = objective.evaluation;
  const metrics = evaluation?.metrics ?? { mae: "—", rmse: "—", r2: 0 };
  const coverage = evaluation ? `${Math.round(evaluation.coverage * 100)}%` : "—";
  const fit = evaluation ? `${Math.round(metrics.r2 * 100)}%` : "—";
  const checks = evaluation?.integrity_checks ?? [];
  return `<section class="insights-workspace"><div class="run-context"><div><span>Selected objective</span><b>OBJ-${String(objective.number).padStart(2, "0")} · ${escapeHtml(objective.title)}</b></div>${icon("arrow")}<div><span>Contract run</span><b>${escapeHtml(objective.run?.run_id ?? "Awaiting run")}</b></div><i>${escapeHtml(objective.run?.status ?? "Pending")}</i></div><div class="insights-layout"><div class="insight-summary"><span class="eyebrow">Seven-day regression</span><h2>Useful evidence—with its limits visible.</h2><div class="confidence-ring"><span><b>${fit}</b><small>variance explained</small></span></div><p>The evaluation covers ${coverage} of ${evaluation?.sample_count ?? "—"} eligible articles. Treat this as planning evidence, not an automatic inventory decision.</p><button data-open-decisions>Use this evidence in Decision Studio ${icon("arrow")}</button></div>
    <div class="feature-panel"><div class="panel-heading"><span>Model evaluation</span><small>Contract metrics</small></div><div class="feature-row"><span>Mean absolute error</span><b></b><small>${metrics.mae}</small></div><div class="feature-row"><span>Root mean squared error</span><b></b><small>${metrics.rmse}</small></div><div class="feature-row"><span>R²</span><b><i style="--width:${Math.max(0, Number(metrics.r2) * 100)}%"></i></b><small>${metrics.r2}</small></div><div class="feature-row"><span>Coverage</span><b><i style="--width:${evaluation ? evaluation.coverage * 100 : 0}%"></i></b><small>${coverage}</small></div><div class="caveat"><b>Provenance</b><span>${escapeHtml(evaluation?.provenance?.model_id ?? "Not available")} · ${escapeHtml(evaluation?.provenance?.dataset_revision ?? "unknown revision")}</span></div></div>
    <div class="cohort-panel"><div class="panel-heading"><span>Integrity checks</span><small>Evaluation contract</small></div>${checks.map((check) => `<button><span><b>${escapeHtml(check.name.replaceAll("_", " "))}</b><small>${escapeHtml(check.detail)}</small></span><strong>${escapeHtml(check.status)}</strong>${icon("arrow")}</button>`).join("")}</div>
  </div></section>`;
}

function decisionsModule(objective) {
  const chosen = selectStrategy(objective.strategy);
  if (state.simulationStatus === "loading") {
    return `<section class="decisions-layout simulation-waiting-layout"><div class="inheritance-banner"><span>${icon("spark")}</span><p><small>Simulation evidence source</small><b>OBJ-${String(objective.number).padStart(2, "0")} → ${escapeHtml(objective.run?.run_id ?? "contract run")}</b></p><i>Inherited · R² ${objective.evaluation?.metrics?.r2 ?? "—"}</i></div>${simulationWaitingMarkup()}</section>`;
  }
  return `<section class="decisions-layout"><div class="inheritance-banner"><span>${icon("spark")}</span><p><small>Simulation evidence source</small><b>OBJ-${String(objective.number).padStart(2, "0")} → ${escapeHtml(objective.run?.run_id ?? "contract run")}</b></p><i>Inherited · R² ${objective.evaluation?.metrics?.r2 ?? "—"}</i></div><div class="evidence-strip"><p><small>Objective</small><b>${escapeHtml(objective.title)}</b></p><p><small>Planning segment</small><b>High-velocity articles</b></p><p><small>Guardrail</small><b>Protect gross margin</b></p><i>${objective.evaluation?.sample_count ?? "—"} evaluated articles</i></div>
    <div class="meeting-panel"><header><span>S</span><p><b>Strategy partner</b><small>Model evidence + scenario model</small></p><i>Working session</i></header><div class="chat-thread"><div class="chat agent"><p>The seven-day model indicates demand concentration in a small set of articles. A blanket markdown could trade away margin. Which merchandising lever should we test first?</p><small>Grounded in the selected objective’s evaluation contract</small></div><div class="chat human"><p>Give predicted high-demand articles more prominent placement without discounting them.</p></div>${objective.chatCount > 2 ? `<div class="chat agent"><p>That preserves price integrity. I’d compare featured placement with replenishment priority and monitor stock-out exposure as the guardrail.</p><small>2 assumptions added to the scenario</small></div>` : ""}</div><form class="strategy-compose"><label for="strategy-input">Ask about an action, offer or merchandising change</label><div><input id="strategy-input" value="How can we protect margin?"><button>${icon("arrow")}</button></div></form></div>
    <div class="intervention-panel"><div class="panel-heading"><span>Candidate interventions</span><small>Scenario layer · ${objective.evaluation?.sample_count ?? "—"} evaluated articles</small></div>${strategies.map((item) => `<button data-strategy="${item.id}" class="intervention ${objective.strategy === item.id ? "selected" : ""}"><span></span><p><b>${item.name}</b><small>${item.detail}</small></p><strong>+${item.lift}%<small>sales</small></strong></button>`).join("")}<div class="strategy-score"><p><small>Expected lift</small><b>+${chosen.lift}%</b></p><p><small>Margin effect</small><b>+${chosen.margin}%</b></p><p><small>Scenario confidence</small><b>${chosen.confidence}%</b></p></div><button class="primary" data-stage-experiment>Stage this experiment ${icon("arrow")}</button></div>
  </section>`;
}

function experimentsModule() {
  return `<section class="experiments-layout"><div class="experiments-heading"><div><span class="eyebrow">Experiment portfolio</span><h2>Measure what happened. Keep what the business learned.</h2><p>Monitor active tests against the success metric and guardrails defined in Business Knowledge.</p></div><button class="secondary" data-new-experiment>${icon("plus")} New experiment</button></div>
    ${state.showExperimentForm ? `<div class="experiment-draft"><div><small>New experiment plan</small><h3>Test another intervention</h3></div><p><span>Population</span><b>High-velocity articles</b></p><p><span>Primary metric</span><b>${state.metric}</b></p><button data-launch-experiment>Start demo test ${icon("arrow")}</button></div>` : ""}
    <div class="active-experiment"><header><div><span></span><p><small>Active · day 6 of 7</small><b>Featured placement</b></p></div><strong>+12.1%<small>item sales</small></strong></header><div class="chart-legend"><span><i></i>Featured placement</span><span><i></i>Business as usual</span></div><svg viewBox="0 0 720 280" preserveAspectRatio="none" aria-label="Experiment performance chart"><g><path d="M0 55H720M0 120H720M0 185H720M0 250H720"/></g><path class="area" d="M0 235 C80 220 90 214 140 205 S230 170 285 178 S370 130 430 140 S520 100 575 90 S665 45 720 50 V280H0Z"/><path class="result" d="M0 235 C80 220 90 214 140 205 S230 170 285 178 S370 130 430 140 S520 100 575 90 S665 45 720 50"/><path class="control" d="M0 240 C90 230 105 223 160 218 S270 205 330 195 S430 184 500 170 S620 160 720 145"/></svg><footer><span>Launch</span><span>Day 2</span><span>Day 4</span><span>Today</span></footer></div>
    <aside class="learning-card"><span>${state.banked ? icon("check") : icon("spark")}</span><small>${state.banked ? "Learning banked" : "Ready to bank"}</small><h3>${state.banked ? "Featured placement improved sales without margin erosion." : "Featured placement is increasing seven-day item sales."}</h3><p>The experiment remains inside the gross-margin and stock-out guardrails.</p><dl><div><dt>Scenario model</dt><dd>${state.banked ? "v1.1" : "v1.0"}</dd></div><div><dt>Model belief</dt><dd>${state.banked ? "+8%" : "Pending"}</dd></div></dl><button data-bank ${state.banked ? "disabled" : ""}>${state.banked ? "Banked to decision memory" : "Bank this learning"} ${icon(state.banked ? "check" : "arrow")}</button></aside>
  </section>`;
}

function moduleContent() {
  return {
    data: dataModule,
    knowledge: knowledgeModule,
    objectives: objectivesModule,
    experiments: experimentsModule,
  }[state.module]();
}

function render() {
  stopWaitingAnimations();
  if (!canAccessModule(state.module, progress())) state.module = "data";
  document.body.className = "decision-room";
  app.innerHTML = shell();
  setQuery();
  saveWorkspaceState(window.localStorage, state);
  bind();
  stopWaitingAnimations = startWaitingAnimations({
    onSimulationComplete: () => {
      if (state.simulationStatus !== "loading") return;
      completeSimulation(state);
      render();
    },
  });
}

function bind() {
  document.querySelectorAll("[data-module]").forEach((button) => button.addEventListener("click", () => { state.module = button.dataset.module; render(); }));
  document.querySelectorAll("[data-source]").forEach((button) => button.addEventListener("click", () => { state.source = button.dataset.source; render(); }));
  document.querySelectorAll("[data-table]").forEach((button) => button.addEventListener("click", () => { state.table = button.dataset.table; render(); }));
  document.querySelectorAll("[data-metric]").forEach((button) => button.addEventListener("click", () => { state.metric = button.dataset.metric; render(); }));
  document.querySelectorAll("[data-guardrail]").forEach((button) => button.addEventListener("click", () => {
    const id = button.dataset.guardrail;
    state.guardrails = state.guardrails.includes(id) ? state.guardrails.filter((item) => item !== id) : [...state.guardrails, id];
    render();
  }));
  document.querySelectorAll("[data-objective-fit]").forEach((button) => button.addEventListener("click", () => {
    const objective = getActiveObjective(state);
    objective.fit = button.dataset.objectiveFit;
    objective.title = objective.fit === "supported" ? "Forecast seven-day item sales" : "Increase in-store visits";
    objective.confirmed = false;
    objective.rtjRun = null;
    state.objectiveView = "brief";
    objective.view = "brief";
    objective.collectionPlan = false;
    objective.materializationStatus = "idle";
    objective.materializationError = null;
    objective.materialization = null;
    objective.apiStatus = "idle";
    objective.apiError = null;
    render();
  }));
  document.querySelectorAll("[data-strategy]").forEach((button) => button.addEventListener("click", () => { getActiveObjective(state).strategy = button.dataset.strategy; render(); }));

  document.querySelector("[data-connect]")?.addEventListener("click", async () => {
    state.apiStatus = "loading";
    state.apiError = null;
    render();
    try {
      const [dataset, defaultTaskCatalog] = await Promise.all([
        api.getDataset(),
        api.getDefaultTasks(),
      ]);
      state.dataset = dataset;
      state.defaultTaskCatalog = defaultTaskCatalog;
      state.connected = true;
      state.apiStatus = "ready";
      state.table = state.dataset.tables[0].name;
    } catch (error) {
      state.connected = false;
      state.apiStatus = "error";
      state.apiError = error.message;
    }
    render();
  });
  document.querySelector("[data-disconnect]")?.addEventListener("click", () => {
    state.connected = false;
    state.dataset = null;
    state.defaultTaskCatalog = null;
    state.apiStatus = "idle";
    state.apiError = null;
    state.knowledgeComplete = false;
    state.objectives = [];
    state.activeObjectiveId = null;
    state.experimentCount = 0;
    state.objectiveView = "brief";
    state.experimentReady = false;
    state.simulationStatus = "idle";
    state.module = "data";
    render();
  });
  document.querySelector("[data-open-knowledge]")?.addEventListener("click", () => { state.module = "knowledge"; render(); });
  document.querySelector("[data-save-knowledge]")?.addEventListener("click", () => {
    if (!businessKnowledgeReady(state.metric, state.guardrails)) return;
    state.knowledgeComplete = true;
    state.module = "objectives";
    state.objectiveView = "brief";
    if (!getActiveObjective(state)) createObjective(state);
    render();
  });
  document.querySelector("[data-new-objective]")?.addEventListener("click", () => {
    createObjective(state);
    render();
  });
  document.querySelectorAll("[data-select-objective]").forEach((button) => button.addEventListener("click", () => { selectObjective(state, button.dataset.selectObjective); render(); }));
  document.querySelectorAll("[data-objective-view]").forEach((button) => button.addEventListener("click", () => {
    state.objectiveView = button.dataset.objectiveView;
    getActiveObjective(state).view = state.objectiveView;
    render();
  }));
  document.querySelector("[data-collection-plan]")?.addEventListener("click", () => { getActiveObjective(state).collectionPlan = true; render(); });
  document.querySelectorAll("[data-default-task]").forEach((button) => button.addEventListener("click", () => {
    const objective = getActiveObjective(state);
    objective.selectedTaskId = button.dataset.defaultTask;
    objective.materializationStatus = "idle";
    objective.materializationError = null;
    objective.materialization = null;
    render();
  }));
  document.querySelector("[data-launch-daytona]")?.addEventListener("click", async () => {
    const objective = getActiveObjective(state);
    objective.materializationStatus = "loading";
    objective.materializationError = null;
    objective.apiStatus = "idle";
    objective.apiError = null;
    render();
    try {
      objective.materialization = await api.launchDaytona([objective.selectedTaskId]);
      objective.materializationStatus = "ready";
    } catch (error) {
      objective.materializationStatus = "error";
      objective.materializationError = error.message;
    }
    render();
  });
  document.querySelector("[data-run-fixture]")?.addEventListener("click", async () => {
    const objective = getActiveObjective(state);
    objective.apiStatus = "loading";
    objective.apiError = null;
    const minimumWait = minimumInferenceWait();
    render();
    try {
      const taskDraft = await api.createTaskDraft(objective.title);
      taskContractFrom(taskDraft);
      const run = await api.getRun("fixture-hm-run");
      const evaluation = await api.getEvaluation(run.run_id);
      const latestRun = state.objectives.reduce((highest, item) => Math.max(highest, item.rtjRun ?? 0), 0);
      await minimumWait;
      objective.taskDraft = taskDraft;
      objective.run = run;
      objective.evaluation = evaluation;
      objective.confirmed = true;
      objective.rtjRun = objective.rtjRun ?? latestRun + 1;
      objective.apiStatus = "ready";
      objective.view = "insights";
      state.module = "objectives";
      state.objectiveView = "insights";
    } catch (error) {
      await minimumWait;
      objective.apiStatus = "error";
      objective.apiError = error.message;
    }
    render();
  });
  document.querySelector("[data-open-decisions]")?.addEventListener("click", () => { state.objectiveView = "decisions"; getActiveObjective(state).view = "decisions"; render(); });
  document.querySelector("[data-stage-experiment]")?.addEventListener("click", () => {
    beginSimulation(state);
    render();
  });
  document.querySelector("[data-bank]")?.addEventListener("click", () => { state.banked = true; render(); });
  document.querySelector("[data-new-experiment]")?.addEventListener("click", () => { state.showExperimentForm = !state.showExperimentForm; render(); });
  document.querySelector("[data-launch-experiment]")?.addEventListener("click", () => { state.experimentCount += 1; state.showExperimentForm = false; render(); });

  document.querySelector(".objective-compose")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const objective = getActiveObjective(state);
    objective.title = document.querySelector("#objective-input").value.trim() || objective.title;
    objective.fit = "supported";
    render();
  });
  document.querySelector(".strategy-compose")?.addEventListener("submit", (event) => { event.preventDefault(); getActiveObjective(state).chatCount = 3; render(); });
}

render();
