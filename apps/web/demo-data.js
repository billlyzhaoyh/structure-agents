export const modules = [
  { id: "data", group: "Foundation", label: "Data connections", hint: "Connect and verify sources" },
  { id: "knowledge", group: "Foundation", label: "Business knowledge", hint: "Metrics, context and guardrails" },
  { id: "objectives", group: "Decision engine", label: "Objectives", hint: "Evidence and decisions by objective" },
  { id: "experiments", group: "Experiments", label: "Experiment portfolio", hint: "Launch, monitor and learn" },
];

export const integrations = [
  { id: "sqldb", mark: "SQL", name: "SQL database", detail: "MySQL · PostgreSQL · SQL Server" },
  { id: "snowflake", mark: "SF", name: "Snowflake", detail: "Cloud data warehouse" },
  { id: "redshift", mark: "RS", name: "AWS Redshift", detail: "Managed data warehouse" },
  { id: "bigquery", mark: "BQ", name: "BigQuery", detail: "Google Cloud warehouse" },
];

export const demoData = {
  short: "Fashion retail demo dataset",
  provenance: { kind: "synthetic", status: "placeholder" },
  industry: "Fashion retail",
  entity: "articles",
  count: "10,400",
  health: "92%",
  rowLabels: { customer: "7.1k", article: "10.4k", transactions: "44.9k" },
  tables: [
    { name: "customer", rows: "7.1k", key: "customer_id", note: "2 columns · 0 relationships" },
    { name: "article", rows: "10.4k", key: "article_id", note: "3 columns · 0 relationships" },
    { name: "transactions", rows: "44.9k", key: "t_dat", note: "5 columns · 2 relationships" },
  ],
  cohorts: [
    ["High-velocity articles", "186", "+22%", "Predicted above their recent seven-day baseline"],
    ["Stable sellers", "492", "+3%", "Predicted close to their recent sales baseline"],
    ["Demand softening", "72", "−18%", "Predicted below their recent seven-day baseline"],
  ],
};

// Demo presentation values for the prediction run. The committed API fixture stays
// synthetic and unexecuted; these are the numbers the demo narrates over it.
export const demoEvaluation = {
  sample_count: 9860,
  coverage: 0.94,
  metrics: { mae: 8.7, rmse: 14.2, r2: 0.61 },
  provenance: {
    dataset_revision: "rel-hm@d8e976fd",
    model_id: "relational foundation model",
    model_revision: "demo placeholder",
    context_length: 512,
    duration_seconds: 43.8,
  },
  integrity_checks: [
    { name: "point_in_time", status: "passed", detail: "Every feature row is bounded by its own prediction timestamp." },
    { name: "prediction_truth_alignment", status: "passed", detail: "Predictions and evaluator truth align on article and prediction timestamp." },
    { name: "masked_test_isolation", status: "passed", detail: "The model package never received evaluator-owned test labels." },
  ],
};

export const simulationStudy = {
  id: "rel-hm/promo-conjoint-v1",
  title: "H&M promotional offer screening",
  decision:
    "Rank promotional offer designs for one eligible customer population to shortlist candidates for a field experiment.",
  population: "Customers with a transaction before 2020-09-07",
  respondents: 400,
  tasksPerRespondent: 10,
  status: "recommended",
};

export const strategies = [
  {
    id: "member-exclusive",
    rank: 1,
    name: "Member exclusive price, 20% off",
    detail: "Member perk framing · no urgency cue · no purchase threshold",
    stability: 0.92,
  },
  {
    id: "percent-off",
    rank: 2,
    name: "Straight 20% off, weekend only",
    detail: "New-season framing · weekend urgency cue",
    stability: 0.78,
  },
  {
    id: "free-shipping",
    rank: 3,
    name: "Free shipping, plain framing",
    detail: "No discount depth or purchase threshold attached",
    stability: 0.64,
  },
];

export const simulationValidation = [
  { gate: "Certification currency", hard: true, status: "passed", summary: "Certification suite is current for the pinned respondent model." },
  { gate: "Design invariants", hard: true, status: "passed", summary: "All 4,000 choice tasks satisfied applicability and balance rules." },
  { gate: "Declared monotonicity", hard: true, status: "passed", summary: "Deeper discounts never reduced simulated choice share." },
  { gate: "Randomization balance", hard: false, status: "passed", summary: "Maximum level imbalance 0.02 across respondents." },
  { gate: "Sentinel repeat variance", hard: false, status: "passed", summary: "Repeat sentinel tasks stayed inside the declared bound at 0.031." },
];

export const simulationDiagnostics = [
  { attribute: "Discount form", level: "Member exclusive price", estimate: 14.2, low: 10.8, high: 17.6, suppressed: false },
  { attribute: "Discount form", level: "Percent off", estimate: 11.5, low: 8.1, high: 14.9, suppressed: false },
  { attribute: "Discount depth", level: "20 percent", estimate: 6.9, low: 4.2, high: 9.6, suppressed: false },
  { attribute: "Framing", level: "Member perk", estimate: 3.1, low: 0.6, high: 5.6, suppressed: false },
  { attribute: "Urgency", level: "Weekend only", estimate: 2.4, low: -0.3, high: 5.1, suppressed: false },
  { attribute: "Purchase threshold", level: "Buy 2", suppressed: true, reason: "Below the declared precision floor" },
];

export const simulationLimitations = [
  "Simulated screening evidence from language-model respondents, not observed customer behaviour.",
  "No causal uplift, incrementality, elasticity or revenue claim is made or implied.",
  "The ranking shortlists candidates for a field experiment; it does not measure business impact.",
];

export function getIntegration(id) {
  return integrations.find((integration) => integration.id === id) ?? integrations[0];
}

export function selectStrategy(id) {
  return strategies.find((strategy) => strategy.id === id) ?? strategies[0];
}

export function canAccessModule(moduleId, progress) {
  switch (moduleId) {
    case "data":
      return true;
    case "knowledge":
      return progress.connected;
    case "objectives":
      return progress.knowledgeComplete;
    case "experiments":
      return progress.experimentReady;
    default:
      return false;
  }
}

export function moduleNavStatus(moduleId, progress) {
  if (moduleId === "data" && progress.connected) return { kind: "complete", label: "Complete" };
  if (moduleId === "knowledge" && progress.knowledgeComplete) return { kind: "complete", label: "Complete" };
  if (moduleId === "objectives" && progress.objectiveCount > 0) {
    return { kind: "activity", label: `${progress.objectiveCount} active` };
  }
  if (moduleId === "experiments" && progress.experimentCount > 0) {
    return { kind: "activity", label: `${progress.experimentCount} active` };
  }
  return { kind: "none", label: "" };
}

export function canAccessObjectiveView(view, objective) {
  if (view === "brief") return true;
  if (view === "insights" || view === "decisions") return Boolean(objective?.confirmed);
  return false;
}

export function businessKnowledgeReady(metric, guardrails) {
  return Boolean(metric?.trim()) && guardrails.length > 0;
}
