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
      throw new ContractApiError(`The StructAgent API returned ${response.status}`, response.status);
    }
    const payload = await response.json();
    if (payload?.contract_version !== "v1") {
      throw new ContractApiError("The API returned an unsupported contract version");
    }
    return payload;
  }

  return {
    getDataset: () => request("/v1/datasets/rel-hm"),
    createTaskDraft: (prompt) => request("/v1/task-drafts", {
      method: "POST",
      body: JSON.stringify({ contract_version: "v1", dataset_id: "rel-hm", prompt }),
    }),
    getRun: (runId) => request(`/v1/runs/${encodeURIComponent(runId)}`),
    getEvaluation: (runId) => request(`/v1/runs/${encodeURIComponent(runId)}/evaluation`),
  };
}

export function taskContractFrom(outcome) {
  if (outcome?.outcome !== "draft_ready" || !outcome.contract) {
    throw new ContractApiError("The objective still needs clarification");
  }
  return outcome.contract;
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
