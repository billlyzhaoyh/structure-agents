import assert from "node:assert/strict";
import test from "node:test";

import {
  businessKnowledgeReady,
  canAccessModule,
  canAccessObjectiveView,
  demoData,
  getIntegration,
  moduleNavStatus,
  modules,
  selectStrategy,
} from "../demo-data.js";

test("only data connections are accessible before a source is loaded", () => {
  const progress = {
    connected: false,
    knowledgeComplete: false,
    rtjReady: false,
    experimentReady: false,
  };

  assert.equal(canAccessModule("data", progress), true);
  assert.equal(canAccessModule("knowledge", progress), false);
  assert.equal(canAccessModule("objectives", progress), false);
});

test("the global navigation treats an objective as the parent work object", () => {
  assert.deepEqual(modules.map(({ id }) => id), ["data", "knowledge", "objectives", "experiments"]);
});

test("only foundation modules use completion status", () => {
  const progress = {
    connected: true,
    knowledgeComplete: true,
    objectiveCount: 2,
    experimentCount: 1,
  };

  assert.deepEqual(moduleNavStatus("data", progress), { kind: "complete", label: "Complete" });
  assert.deepEqual(moduleNavStatus("knowledge", progress), { kind: "complete", label: "Complete" });
  assert.deepEqual(moduleNavStatus("objectives", progress), { kind: "activity", label: "2 active" });
  assert.deepEqual(moduleNavStatus("experiments", progress), { kind: "activity", label: "1 active" });
});

test("module access follows product prerequisites rather than page order", () => {
  const connected = {
    connected: true,
    knowledgeComplete: false,
    rtjReady: false,
    experimentReady: false,
  };
  assert.equal(canAccessModule("knowledge", connected), true);
  assert.equal(canAccessModule("objectives", connected), false);

  const knowledgeReady = { ...connected, knowledgeComplete: true };
  assert.equal(canAccessModule("objectives", knowledgeReady), true);
  const beliefReady = { ...knowledgeReady, rtjReady: true };
  assert.equal(canAccessModule("experiments", beliefReady), false);

  const experimentReady = { ...beliefReady, experimentReady: true };
  assert.equal(canAccessModule("experiments", experimentReady), true);
});

test("insights and decisions belong to a confirmed objective", () => {
  assert.equal(canAccessObjectiveView("brief", { confirmed: false }), true);
  assert.equal(canAccessObjectiveView("insights", { confirmed: false }), false);
  assert.equal(canAccessObjectiveView("decisions", { confirmed: false }), false);
  assert.equal(canAccessObjectiveView("insights", { confirmed: true }), true);
  assert.equal(canAccessObjectiveView("decisions", { confirmed: true }), true);
});

test("business knowledge requires both a success metric and a guardrail", () => {
  assert.equal(businessKnowledgeReady("Repeat purchase rate", ["margin"]), true);
  assert.equal(businessKnowledgeReady("Repeat purchase rate", []), false);
  assert.equal(businessKnowledgeReady("", ["margin"]), false);
});

test("a shortlist selection exposes the ranked simulation profile", () => {
  assert.deepEqual(selectStrategy("free-shipping"), {
    id: "free-shipping",
    rank: 3,
    name: "Free shipping, plain framing",
    detail: "No discount depth or purchase threshold attached",
    stability: 0.64,
  });
});

test("an unknown shortlist id falls back to the top-ranked profile", () => {
  assert.equal(selectStrategy("missing").rank, 1);
});

test("the frontend schema fallback follows the V1 retail table conventions", () => {
  assert.deepEqual(demoData.tables.map(({ name }) => name), ["customer", "article", "transactions"]);
  assert.equal(demoData.tables.find(({ name }) => name === "transactions").key, "t_dat");
});

test("the mock integration catalogue resolves supported and unknown sources", () => {
  assert.equal(getIntegration("snowflake").name, "Snowflake");
  assert.equal(getIntegration("redshift").name, "AWS Redshift");
  assert.equal(getIntegration("unknown").id, "sqldb");
});
