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

test("the client rejects unavailable and incompatible APIs", async () => {
  const unavailable = createApiClient({ fetchImpl: async () => { throw new Error("offline"); } });
  const incompatible = createApiClient({ fetchImpl: async () => response({ contract_version: "v2" }) });

  await assert.rejects(unavailable.getDataset(), /unavailable/);
  await assert.rejects(incompatible.getDataset(), /unsupported contract version/);
});

test("task outcomes must be ready before the UI can run them", () => {
  const contract = { horizon: { value: 7, unit: "days" } };

  assert.equal(taskContractFrom({ outcome: "draft_ready", contract }), contract);
  assert.throws(
    () => taskContractFrom({ outcome: "needs_clarification", questions: [] }),
    ContractApiError,
  );
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
