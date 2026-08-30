import assert from "node:assert/strict";
import test from "node:test";

import {
  createObjective,
  createWorkspaceState,
  getActiveObjective,
  loadWorkspaceState,
  saveWorkspaceState,
  selectObjective,
  WORKSPACE_STORAGE_KEY,
  workspaceProgress,
} from "../workspace-state.js";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}

test("objectives are independent records that can be selected", () => {
  const state = createWorkspaceState({ connected: true, knowledgeComplete: true });
  const first = createObjective(state, "Reduce churn");
  first.confirmed = true;
  first.rtjRun = 1;
  const second = createObjective(state, "Increase repeat purchase");

  assert.equal(getActiveObjective(state).id, second.id);
  assert.equal(getActiveObjective(state).confirmed, false);
  assert.equal(selectObjective(state, first.id).title, "Reduce churn");
  assert.equal(getActiveObjective(state).rtjRun, 1);
});

test("workspace progress is derived from objective records", () => {
  const state = createWorkspaceState({ connected: true, knowledgeComplete: true });
  const first = createObjective(state, "Reduce churn");
  first.confirmed = true;
  first.rtjRun = 1;
  createObjective(state, "Draft objective");

  assert.deepEqual(workspaceProgress(state), {
    connected: true,
    knowledgeComplete: true,
    experimentReady: false,
    objectiveCount: 2,
    rtjRunCount: 1,
    experimentCount: 0,
  });
});

test("workspace state survives a browser refresh", () => {
  const storage = memoryStorage();
  const state = createWorkspaceState({ connected: true, knowledgeComplete: true, module: "objectives" });
  createObjective(state, "Reduce churn");

  assert.equal(saveWorkspaceState(storage, state), true);
  assert.match(storage.getItem(WORKSPACE_STORAGE_KEY), /Reduce churn/);
  assert.deepEqual(loadWorkspaceState(storage), state);
});

test("invalid persisted state falls back safely", () => {
  const storage = memoryStorage();
  storage.setItem(WORKSPACE_STORAGE_KEY, "not json");
  assert.equal(loadWorkspaceState(storage), null);
});
