const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export class ContractApiError extends Error {
  constructor(message, status = null) {
    super(message);
    this.name = "ContractApiError";
    this.status = status;
  }
}

export function createApiClient({ baseUrl = DEFAULT_API_BASE, fetchImpl = globalThis.fetch } = {}) {
  if (typeof fetchImpl !== "function") throw new ContractApiError("Fetch is unavailable");

  async function request(path, options = {}) {
    let response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        ...options,
        headers: { "Content-Type": "application/json", ...options.headers },
      });
    } catch {
      throw new ContractApiError("The local StructAgent API is unavailable");
    }

    if (!response.ok) {
      let errorPayload = null;
      try {
        errorPayload = await response.json();
      } catch {
        // The status remains useful when an upstream proxy returns a non-JSON body.
      }
      const compilerUnavailable = response.status === 503 && path.startsWith("/v1/task-drafts");
      const fallback = compilerUnavailable
        ? "The StructAgent task compiler is unavailable"
        : `The StructAgent API returned ${response.status}`;
      const message = errorPayload?.detail?.message ?? fallback;
      throw new ContractApiError(message, response.status);
    }
    const payload = await response.json();
    if (payload?.contract_version !== "v1") {
      throw new ContractApiError("The API returned an unsupported contract version");
    }
    return payload;
  }

  return {
    getDataset: () => request("/v1/datasets/rel-hm"),
    getDefaultTasks: () => request("/v1/tasks/defaults?dataset_id=rel-hm"),
    launchDaytona: (taskIds) => request("/v1/materializations/daytona", {
      method: "POST",
      body: JSON.stringify({
        contract_version: "v1",
        dataset_id: "rel-hm",
        task_ids: taskIds,
        approved: true,
      }),
    }),
    createTaskDraft: (prompt) => request("/v1/task-drafts", {
      method: "POST",
      body: JSON.stringify({ contract_version: "v1", dataset_id: "rel-hm", prompt }),
    }),
    clarifyTaskDraft: (draftId, clarification) => request(
      `/v1/task-drafts/${encodeURIComponent(draftId)}/clarifications`,
      { method: "POST", body: JSON.stringify(clarification) },
    ),
    runSimulatedInference: (taskId, taskType) => request("/v1/inferences/simulated", {
      method: "POST",
      body: JSON.stringify({
        contract_version: "v1",
        dataset_id: "rel-hm",
        task_id: taskId,
        task_type: taskType,
      }),
    }),
    runModalInference: () => request("/v1/inferences/modal", {
      method: "POST",
      body: JSON.stringify({
        contract_version: "v1",
        dataset_id: "rel-hm",
        task_id: "rel-hm/user-churn",
        approved: true,
      }),
    }),
    getRun: (runId) => request(`/v1/runs/${encodeURIComponent(runId)}`),
    getEvaluation: (runId) => request(`/v1/runs/${encodeURIComponent(runId)}/evaluation`),
  };
}

export function taskContractFrom(outcome) {
  if (outcome?.outcome === "needs_clarification" || outcome?.outcome === "unsupported") return null;
  if (outcome?.outcome === "draft_ready" && outcome.contract) return outcome.contract;
  throw new ContractApiError("The task compiler returned an invalid outcome");
}

export function tableViewModels(dataset, rowLabels = {}) {
  return dataset.tables.map((table) => {
    const primaryKey = table.columns.find((column) => column.primary_key)?.name ?? null;
    const foreignKeys = table.columns.filter((column) => column.foreign_key).length;
    return {
      name: table.name,
      key: primaryKey ?? table.columns.find((column) => column.time_column)?.name ?? "No primary key",
      detail: `${table.columns.length} columns · ${foreignKeys} relationship${foreignKeys === 1 ? "" : "s"}`,
      rows: rowLabels[table.name] ?? "Metadata",
    };
  });
}
