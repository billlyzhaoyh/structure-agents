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
import {
  createObjective,
  createWorkspaceState,
  getActiveObjective,
  loadWorkspaceState,
  saveWorkspaceState,
  selectObjective,
  workspaceProgress,
} from "./workspace-state.js";

const app = document.querySelector("#app");
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
  objectives: ["Objectives", "Each objective carries its own business brief, RT-J evidence and decision work."],
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
  return `<section class="integration-layout">
    <div class="section-intro"><span class="eyebrow">Connect a source</span><h2>Where does your business data live?</h2><p>Choose an integration to load the fashion retail demo dataset. No credentials are requested.</p></div>
    <div class="source-grid" aria-label="Database integrations">${integrations.map((source) => `<button data-source="${source.id}" class="source-card ${state.source === source.id ? "selected" : ""}"><span>${source.mark}</span><p><b>${source.name}</b><small>${source.detail}</small></p><i>${state.source === source.id ? icon("check") : "Choose"}</i></button>`).join("")}</div>
    <div class="connection-panel"><header><span>${selected.mark}</span><p><small>Selected integration</small><b>${selected.name}</b></p><i>Demo connection</i></header>
      <div class="mock-fields"><p><small>Host</small><b>fashion-demo.sql.local</b></p><p><small>Database</small><b>retail_warehouse</b></p><p><small>Schema</small><b>public</b></p><p><small>Access</small><b>Read-only</b></p></div>
      <footer><p><b>No credentials are used.</b><small>Continuing loads the fashion retail demo dataset.</small></p><button data-connect>Connect ${selected.name} ${icon("arrow")}</button></footer>
    </div>
    <div class="security-note">${icon("lock")}<p><b>Read-only access</b><small>The demo displays schema access without collecting or storing warehouse credentials.</small></p></div>
  </section>`;
}

function tableExplorer() {
  const data = demoData;
  return `<div class="table-explorer"><div class="table-list">${data.tables.map((table) => `<button data-table="${table.name}" class="${state.table === table.name ? "active" : ""}"><span>${icon("database")}</span><p><b>${table.name}</b><small>${table.rows} rows · ${table.note}</small></p></button>`).join("")}</div>
    <div class="relation-canvas"><svg viewBox="0 0 640 300" preserveAspectRatio="none" aria-hidden="true"><path d="M130 80 C260 80 220 150 320 150 S420 65 525 65"/><path d="M130 80 C250 80 220 245 350 245 S440 205 525 205"/><path d="M320 150 C390 150 420 205 525 205"/></svg>
      <button class="node node-a ${state.table === "customers" ? "active" : ""}" data-table="customers"><small>identity</small><b>customers</b><span>customer_id</span></button>
      <button class="node node-b ${state.table === "transactions" ? "active" : ""}" data-table="transactions"><small>event</small><b>transactions</b><span>transaction_id</span></button>
      <button class="node node-c ${state.table === "articles" ? "active" : ""}" data-table="articles"><small>entity</small><b>articles</b><span>article_id</span></button>
      <button class="node node-d ${state.table === "departments" ? "active" : ""}" data-table="departments"><small>taxonomy</small><b>departments</b><span>department_id</span></button>
      <div class="canvas-status"><span></span><p><b>Structure understood</b><small>3 relationships · no orphan keys</small></p></div>
    </div></div>`;
}

function dataModule() {
  if (!state.connected) return integrationChooser();
  return `<section class="data-module"><div class="section-intro with-action"><div><span class="eyebrow">Connected data</span><h2>Your fashion retail data has a shape.</h2><p>We found ${demoData.count} shoppers across four related tables. Verify the relationships before StructAgent uses them.</p></div><button class="secondary" data-disconnect>Change integration</button></div>
    <div class="connection-ready"><span></span><p><small>${getIntegration(state.source).name} · read-only</small><b>${demoData.short}</b></p><i>${icon("check")} Connected</i></div>
    ${tableExplorer()}
    <div class="data-receipt"><p><small>Coverage</small><b>${demoData.health}</b></p><p><small>Relationships</small><b>3 healthy</b></p><p><small>Fresh through</small><b>29 Aug</b></p><button data-open-knowledge>Open business knowledge ${icon("arrow")}</button></div>
  </section>`;
}

function knowledgeModule() {
  const metricOptions = ["Repeat purchase rate", "Item sales", "Conversion rate", "Gross margin"];
  const guardrails = [
    ["margin", "Gross margin", "Do not reduce"],
    ["optouts", "Customer opt-outs", "Keep below 1.5%"],
    ["discount", "Discount exposure", "No blanket markdowns"],
  ];
  return `<section class="knowledge-layout"><div class="section-intro"><span class="eyebrow">Knowledge centre</span><h2>The system needs your definition of a good decision.</h2><p>Connected data describes what happened. Business knowledge tells StructAgent which outcomes matter and which trade-offs are unacceptable.</p></div>
    <div class="knowledge-card business-context"><label for="business-context">How the business works</label><textarea id="business-context">We are a growing fashion retailer. Most sales come from returning shoppers, and we want sustainable growth without relying on blanket discounts.</textarea><small>Plain language is useful. This stays editable.</small></div>
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
    ["insights", "Customer insights", objective.confirmed ? `RT-J r${objective.rtjRun}` : "Run RT-J first"],
    ["decisions", "Decision Studio", objective.confirmed ? `Uses RT-J r${objective.rtjRun}` : "Waiting for evidence"],
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
    <div class="chat-thread objective-thread"><div class="chat agent"><p>What business outcome should we improve first?</p><small>I’ll check the available data, sharpen the objective, and prepare the RT-J task with you.</small></div>
      ${objective.fit ? `<div class="chat human"><p>${escapeHtml(objective.title)}</p></div>${objectiveAgentGuidance(objective)}` : ""}
    </div>
    <div class="objective-prompts"><span>Suggested starts</span><button data-objective-fit="supported"><b>Reduce shopper churn</b><small>Supported by current data</small></button><button data-objective-fit="unsupported"><b>Increase store footfall</b><small>Needs additional data</small></button></div>
    <form class="objective-compose"><label for="objective-input">Describe the objective in your own words</label><div><input id="objective-input" value="${escapeHtml(objective.title === "Define a business outcome" ? "Reduce shopper churn without blanket discounts" : objective.title)}"><button>${icon("arrow")}</button></div></form>
  </div>`;
}

function objectiveAgentGuidance(objective) {
  if (objective.fit === "unsupported") {
    return `<div class="chat agent agent-task data-gap"><div class="agent-task-status"><span>${icon("warning")}</span><p><small>Data check</small><b>We need one more source before creating this task.</b></p></div><p>Purchases cannot show who entered a store without buying. I’ve paused this objective so the resulting model does not create false confidence.</p><div class="missing-data"><b>Data to collect</b><span>store_id</span><span>visit_timestamp</span><span>customer_id or cohort</span></div>${objective.collectionPlan ? `<div class="plan-ready">${icon("check")}<p><b>Collection plan created</b><small>Add store-visit events, validate identity coverage, then return to this conversation.</small></p></div>` : `<button class="agent-action" data-collection-plan>Create data collection plan ${icon("arrow")}</button>`}</div>`;
  }
  if (objective.confirmed) {
    return `<div class="chat agent agent-task"><div class="agent-task-status"><span>${icon("check")}</span><p><small>Objective ready</small><b>The RT-J task is defined and linked to this objective.</b></p></div><div class="task-preview"><p><small>Population</small><b>Returning shoppers</b></p><p><small>Outcome window</small><b>30 days</b></p><p><small>Task</small><b>Disengagement prediction</b></p></div><button class="agent-action" data-objective-view="insights">Open customer insights ${icon("arrow")}</button></div>`;
  }
  return `<div class="chat agent agent-task"><div class="agent-task-status"><span>${icon("check")}</span><p><small>Supported by current data</small><b>I can turn this into a credible RT-J task.</b></p></div><p>Purchase timing, article affinity and discount reliance provide useful signals. I’ve translated the conversation into the task below.</p><div class="task-contract"><small>Proposed task</small><p>For each returning shopper, estimate 30-day disengagement using only information known today.</p></div><div class="task-preview"><p><small>Population</small><b>Returning shoppers</b></p><p><small>Outcome window</small><b>30 days</b></p><p><small>Guardrail</small><b>Protect margin</b></p></div><button class="agent-action" data-run-rtj>Create objective and RT-J task ${icon("arrow")}</button></div>`;
}

function insightsModule(objective) {
  return `<section class="insights-workspace"><div class="run-context"><div><span>Selected objective</span><b>OBJ-${String(objective.number).padStart(2, "0")} · ${escapeHtml(objective.title)}</b></div>${icon("arrow")}<div><span>Evidence run</span><b>RT-J r${objective.rtjRun} · Latest</b></div><i>Ready for simulation</i></div><div class="insights-layout"><div class="insight-summary"><span class="eyebrow">RT-J demo run</span><h2>A useful belief—with its limits visible.</h2><div class="confidence-ring"><span><b>81%</b><small>decision confidence</small></span></div><p>Strong enough to understand churn risk and compare targeted strategies. Not suitable for automatic customer decisions.</p><button data-open-decisions>Use this evidence in Decision Studio ${icon("arrow")}</button></div>
    <div class="feature-panel"><div class="panel-heading"><span>What shapes the belief</span><small>Relative influence</small></div>${demoData.features.map(([name, value]) => `<div class="feature-row"><span>${name}</span><b><i style="--width:${value}%"></i></b><small>${value}</small></div>`).join("")}<div class="caveat"><b>Watch-out</b><span>Predictions are least certain for first-time shoppers.</span></div></div>
    <div class="cohort-panel"><div class="panel-heading"><span>Customer insights</span><small>30-day churn risk</small></div>${demoData.cohorts.map((item) => `<button><span><b>${item[0]}</b><small>${item[3]}</small></span><strong>${item[2]}</strong>${icon("arrow")}</button>`).join("")}</div>
  </div></section>`;
}

function decisionsModule(objective) {
  const chosen = selectStrategy(objective.strategy);
  return `<section class="decisions-layout"><div class="inheritance-banner"><span>${icon("spark")}</span><p><small>Simulation evidence source</small><b>OBJ-${String(objective.number).padStart(2, "0")} → RT-J r${objective.rtjRun}</b></p><i>Inherited · 81% confidence</i></div><div class="evidence-strip"><p><small>Objective</small><b>${escapeHtml(objective.title)}</b></p><p><small>Priority cohort</small><b>Seasonal loyalists</b></p><p><small>Guardrail</small><b>Protect gross margin</b></p><i>7,106 profiles available</i></div>
    <div class="meeting-panel"><header><span>S</span><p><b>Strategy partner</b><small>RT-J evidence + customer model</small></p><i>Working session</i></header><div class="chat-thread"><div class="chat agent"><p>Seasonal loyalists return for a narrow edit, but visits are slowing. A blanket markdown may trade away margin. What could make returning feel worthwhile?</p><small>Based on 1,580 demo shopper profiles</small></div><div class="chat human"><p>Offer a personal preview of the new-season edit without discounting it.</p></div>${objective.chatCount > 2 ? `<div class="chat agent"><p>That preserves price integrity. I’d compare the preview against a curated outfit edit and cap frequency so the invitation stays meaningful.</p><small>2 assumptions added to the simulation</small></div>` : ""}</div><form class="strategy-compose"><label for="strategy-input">Ask about an action, offer or message</label><div><input id="strategy-input" value="How can we protect margin?"><button>${icon("arrow")}</button></div></form></div>
    <div class="intervention-panel"><div class="panel-heading"><span>Candidate interventions</span><small>Evaluated across 7,106 demo profiles</small></div>${strategies.map((item) => `<button data-strategy="${item.id}" class="intervention ${objective.strategy === item.id ? "selected" : ""}"><span></span><p><b>${item.name}</b><small>${item.detail}</small></p><strong>+${item.lift}%<small>retained</small></strong></button>`).join("")}<div class="strategy-score"><p><small>Expected lift</small><b>+${chosen.lift}%</b></p><p><small>Margin effect</small><b>+${chosen.margin}%</b></p><p><small>Confidence</small><b>${chosen.confidence}%</b></p></div><button class="primary" data-stage-experiment>Stage this experiment ${icon("arrow")}</button></div>
  </section>`;
}

function experimentsModule() {
  return `<section class="experiments-layout"><div class="experiments-heading"><div><span class="eyebrow">Experiment portfolio</span><h2>Measure what happened. Keep what the business learned.</h2><p>Monitor active tests against the success metric and guardrails defined in Business Knowledge.</p></div><button class="secondary" data-new-experiment>${icon("plus")} New experiment</button></div>
    ${state.showExperimentForm ? `<div class="experiment-draft"><div><small>New experiment plan</small><h3>Test another intervention</h3></div><p><span>Population</span><b>Seasonal loyalists</b></p><p><span>Primary metric</span><b>${state.metric}</b></p><button data-launch-experiment>Start demo test ${icon("arrow")}</button></div>` : ""}
    <div class="active-experiment"><header><div><span></span><p><small>Active · day 18 of 30</small><b>New-season preview</b></p></div><strong>+12.1%<small>repeat visits</small></strong></header><div class="chart-legend"><span><i></i>New-season preview</span><span><i></i>Business as usual</span></div><svg viewBox="0 0 720 280" preserveAspectRatio="none" aria-label="Experiment performance chart"><g><path d="M0 55H720M0 120H720M0 185H720M0 250H720"/></g><path class="area" d="M0 235 C80 220 90 214 140 205 S230 170 285 178 S370 130 430 140 S520 100 575 90 S665 45 720 50 V280H0Z"/><path class="result" d="M0 235 C80 220 90 214 140 205 S230 170 285 178 S370 130 430 140 S520 100 575 90 S665 45 720 50"/><path class="control" d="M0 240 C90 230 105 223 160 218 S270 205 330 195 S430 184 500 170 S620 160 720 145"/></svg><footer><span>Launch</span><span>Day 6</span><span>Day 12</span><span>Today</span></footer></div>
    <aside class="learning-card"><span>${state.banked ? icon("check") : icon("spark")}</span><small>${state.banked ? "Learning banked" : "Ready to bank"}</small><h3>${state.banked ? "Seasonal loyalists value access over markdowns." : "A new-season preview is driving return visits."}</h3><p>The demo cohort shows stable margin and no material segment disparity.</p><dl><div><dt>Customer twin</dt><dd>${state.banked ? "v1.1" : "v1.0"}</dd></div><div><dt>Model belief</dt><dd>${state.banked ? "+8%" : "Pending"}</dd></div></dl><button data-bank ${state.banked ? "disabled" : ""}>${state.banked ? "Banked to decision memory" : "Bank this learning"} ${icon(state.banked ? "check" : "arrow")}</button></aside>
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
  if (!canAccessModule(state.module, progress())) state.module = "data";
  document.body.className = "decision-room";
  app.innerHTML = shell();
  setQuery();
  saveWorkspaceState(window.localStorage, state);
  bind();
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
    objective.title = objective.fit === "supported" ? "Reduce 30-day shopper churn" : "Increase in-store visits";
    objective.confirmed = false;
    objective.rtjRun = null;
    state.objectiveView = "brief";
    objective.view = "brief";
    objective.collectionPlan = false;
    render();
  }));
  document.querySelectorAll("[data-strategy]").forEach((button) => button.addEventListener("click", () => { getActiveObjective(state).strategy = button.dataset.strategy; render(); }));

  document.querySelector("[data-connect]")?.addEventListener("click", () => { state.connected = true; render(); });
  document.querySelector("[data-disconnect]")?.addEventListener("click", () => {
    state.connected = false;
    state.knowledgeComplete = false;
    state.objectives = [];
    state.activeObjectiveId = null;
    state.experimentCount = 0;
    state.objectiveView = "brief";
    state.experimentReady = false;
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
  document.querySelector("[data-run-rtj]")?.addEventListener("click", () => {
    const objective = getActiveObjective(state);
    const latestRun = state.objectives.reduce((highest, item) => Math.max(highest, item.rtjRun ?? 0), 0);
    objective.confirmed = true;
    objective.rtjRun = objective.rtjRun ?? latestRun + 1;
    objective.view = "insights";
    state.module = "objectives";
    state.objectiveView = "insights";
    render();
  });
  document.querySelector("[data-open-decisions]")?.addEventListener("click", () => { state.objectiveView = "decisions"; getActiveObjective(state).view = "decisions"; render(); });
  document.querySelector("[data-stage-experiment]")?.addEventListener("click", () => {
    state.experimentReady = true;
    state.experimentCount = Math.max(1, state.experimentCount);
    state.module = "experiments";
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
