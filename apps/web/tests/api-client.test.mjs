import assert from "node:assert/strict";
import test from "node:test";

import {
  ContractApiError,
  createApiClient,
  tableViewModels,
  taskContractFrom,
} from "../api-client.js";

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => payload };
}

test("the client sends a versioned H&M task-draft request", async () => {
  const calls = [];
  const client = createApiClient({
    baseUrl: "http://api.test",
    fetchImpl: async (...args) => {
      calls.push(args);
      return response({ contract_version: "v1", outcome: "draft_ready", contract: {} });
    },
  });

  await client.createTaskDraft("Forecast item sales over the next seven days");

  assert.equal(calls[0][0], "http://api.test/v1/task-drafts");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    contract_version: "v1",
    dataset_id: "rel-hm",
    prompt: "Forecast item sales over the next seven days",
  });
});

test("the client launches an explicitly approved reviewed task in Daytona", async () => {
  const calls = [];
  const client = createApiClient({
    baseUrl: "http://api.test",
    fetchImpl: async (...args) => {
      calls.push(args);
      return response({ contract_version: "v1", status: "succeeded", tasks: [] });
    },
  });

  await client.launchDaytona(["rel-hm/user-churn"]);

  assert.equal(calls[0][0], "http://api.test/v1/materializations/daytona");
  assert.equal(calls[0][1].method, "POST");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    contract_version: "v1",
    dataset_id: "rel-hm",
    task_ids: ["rel-hm/user-churn"],
    approved: true,
  });
});

test("the client loads the reviewed rel-hm default-task catalog", async () => {
  const calls = [];
  const client = createApiClient({
    baseUrl: "http://api.test",
    fetchImpl: async (...args) => {
      calls.push(args);
      return response({ contract_version: "v1", tasks: [] });
    },
  });

  await client.getDefaultTasks();

  assert.equal(calls[0][0], "http://api.test/v1/tasks/defaults?dataset_id=rel-hm");
});

test("the client surfaces sanitized API failure details", async () => {
  const client = createApiClient({
    fetchImpl: async () => response(
      { detail: { code: "missing_credential", message: "Server credential is unavailable" } },
      { ok: false, status: 503 },
    ),
  });

  await assert.rejects(client.launchDaytona(["rel-hm/item-sales"]), {
    name: "ContractApiError",
    message: "Server credential is unavailable",
    status: 503,
  });
});

test("the client rejects unavailable and incompatible APIs", async () => {
  const unavailable = createApiClient({ fetchImpl: async () => { throw new Error("offline"); } });
  const incompatible = createApiClient({ fetchImpl: async () => response({ contract_version: "v2" }) });

  await assert.rejects(unavailable.getDataset(), /unavailable/);
  await assert.rejects(incompatible.getDataset(), /unsupported contract version/);
});

test("clarification and unsupported responses are normal non-runnable outcomes", () => {
  const contract = { horizon: { value: 7, unit: "days" } };

  assert.equal(taskContractFrom({ outcome: "draft_ready", contract }), contract);
  assert.equal(taskContractFrom({ outcome: "needs_clarification", questions: [] }), null);
  assert.equal(taskContractFrom({ outcome: "unsupported", reason_code: "unsupported_target" }), null);
  assert.throws(() => taskContractFrom({ outcome: "unknown" }), ContractApiError);
});

test("clarification requests carry cumulative history to the stateless route", async () => {
  const calls = [];
  const client = createApiClient({
    baseUrl: "http://api.test",
    fetchImpl: async (...args) => {
      calls.push(args);
      return response({ contract_version: "v1", outcome: "needs_clarification", questions: [] });
    },
  });
  const payload = {
    contract_version: "v1",
    dataset_id: "rel-hm",
    original_prompt: "Predict demand",
    prior_questions: [{ question_id: "horizon" }],
    answers: [{ question_id: "horizon", value: "7 days" }],
  };

  await client.clarifyTaskDraft("draft_abc", payload);

  assert.equal(calls[0][0], "http://api.test/v1/task-drafts/draft_abc/clarifications");
  assert.deepEqual(JSON.parse(calls[0][1].body), payload);
});

test("503 is exposed as an explicit compiler unavailable state", async () => {
  const client = createApiClient({ fetchImpl: async () => response({}, { ok: false, status: 503 }) });

  await assert.rejects(client.createTaskDraft("Predict demand"), (error) => {
    assert.equal(error.status, 503);
    assert.match(error.message, /compiler is unavailable/);
    return true;
  });
});

test("dataset descriptors map to the schema explorer without inventing keys", () => {
  const tables = tableViewModels({
    tables: [
      { name: "article", columns: [{ name: "article_id", primary_key: true }] },
      {
        name: "transactions",
        columns: [
          { name: "article_id", foreign_key: { table: "article", column: "article_id" } },
          { name: "t_dat", time_column: true },
        ],
      },
    ],
  });

  assert.deepEqual(tables, [
    { name: "article", key: "article_id", detail: "1 columns · 0 relationships", rows: "Metadata" },
    { name: "transactions", key: "t_dat", detail: "2 columns · 1 relationship", rows: "Metadata" },
  ]);
});
