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

export const strategies = [
  {
    id: "early",
    name: "Featured placement",
    detail: "Give high-velocity articles more prominent placement without discounting.",
    lift: 11.8,
    margin: 7.2,
    confidence: 81,
  },
  {
    id: "credit",
    name: "Replenishment priority",
    detail: "Move predicted high-demand articles forward in replenishment planning.",
    lift: 16.4,
    margin: 2.1,
    confidence: 74,
  },
  {
    id: "bundle",
    name: "Coordinated outfit placement",
    detail: "Place complementary articles beside predicted high-demand products.",
    lift: 9.6,
    margin: 9.1,
    confidence: 86,
  },
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
