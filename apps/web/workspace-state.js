export const WORKSPACE_STORAGE_KEY = "structagent.fashion-retail.workspace.v2";

export function createWorkspaceState(overrides = {}) {
  return {
    module: "data",
    objectiveView: "brief",
    connected: false,
    knowledgeComplete: false,
    experimentCount: 0,
    experimentReady: false,
    simulationStatus: "idle",
    banked: false,
    apiStatus: "idle",
    apiError: null,
    dataset: null,
    source: "sqldb",
    table: "customer",
    metric: "Item sales",
    guardrails: ["margin", "stockouts"],
    objectives: [],
    activeObjectiveId: null,
    showExperimentForm: false,
    ...overrides,
  };
}

export function createObjective(state, title = "Define a business outcome") {
  const nextNumber = state.objectives.reduce((highest, item) => Math.max(highest, item.number), 0) + 1;
  const objective = {
    id: `objective-${nextNumber}`,
    number: nextNumber,
    title,
    fit: null,
    confirmed: false,
    rtjRun: null,
    taskDraft: null,
    run: null,
    evaluation: null,
    apiStatus: "idle",
    apiError: null,
    collectionPlan: false,
    strategy: "early",
    chatCount: 2,
    view: "brief",
  };
  state.objectives.push(objective);
  state.activeObjectiveId = objective.id;
  state.objectiveView = "brief";
  return objective;
}

export function getActiveObjective(state) {
  return state.objectives.find((item) => item.id === state.activeObjectiveId) ?? null;
}

export function selectObjective(state, objectiveId) {
  const objective = state.objectives.find((item) => item.id === objectiveId);
  if (!objective) return null;
  state.activeObjectiveId = objective.id;
  state.objectiveView = objective.view;
  return objective;
}

export function workspaceProgress(state) {
  const confirmed = state.objectives.filter((item) => item.confirmed);
  return {
    connected: state.connected,
    knowledgeComplete: state.knowledgeComplete,
    experimentReady: state.experimentReady,
    objectiveCount: state.objectives.length,
    rtjRunCount: confirmed.filter((item) => item.rtjRun).length,
    experimentCount: state.experimentCount,
  };
}

export function beginSimulation(state) {
  state.simulationStatus = "loading";
}

export function completeSimulation(state) {
  state.simulationStatus = "ready";
  state.experimentReady = true;
  state.experimentCount = Math.max(1, state.experimentCount);
  state.module = "experiments";
}

export function saveWorkspaceState(storage, state) {
  try {
    storage?.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify({ version: 2, state }));
    return true;
  } catch {
    return false;
  }
}

export function loadWorkspaceState(storage) {
  try {
    const stored = JSON.parse(storage?.getItem(WORKSPACE_STORAGE_KEY));
    if (stored?.version !== 2 || !stored.state || !Array.isArray(stored.state.objectives)) return null;
    return createWorkspaceState(stored.state);
  } catch {
    return null;
  }
}
