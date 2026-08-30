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
  entity: "shoppers",
  count: "7,106",
  health: "92%",
  tables: [
    { name: "customers", rows: "7.1k", key: "customer_id", note: "shopper profile" },
    { name: "articles", rows: "10.4k", key: "article_id", note: "product catalogue" },
    { name: "transactions", rows: "44.9k", key: "transaction_id", note: "basket history" },
    { name: "departments", rows: "250", key: "department_id", note: "merchandising" },
  ],
  features: [
    ["Weeks since last visit", 82],
    ["Seasonal affinity", 76],
    ["Basket complementarity", 61],
    ["Discount reliance", 39],
  ],
  cohorts: [
    ["Seasonal loyalists", "1,580", "26%", "Returns for a narrow seasonal edit"],
    ["Outfit builders", "734", "15%", "Buys coordinated items in short bursts"],
    ["Sale-only drifters", "1,108", "38%", "Responds strongly to markdowns"],
  ],
};

export const strategies = [
  {
    id: "early",
    name: "New-season preview",
    detail: "Invite seasonal loyalists to a personal preview without discounting.",
    lift: 11.8,
    margin: 7.2,
    confidence: 81,
  },
  {
    id: "credit",
    name: "£8 comeback credit",
    detail: "Offer sale-only drifters a time-boxed account credit.",
    lift: 16.4,
    margin: 2.1,
    confidence: 74,
  },
  {
    id: "bundle",
    name: "Curated outfit edit",
    detail: "Pair a familiar article with one useful outfit addition.",
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
