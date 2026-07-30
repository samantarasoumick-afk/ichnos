"use client";

import { useEffect, useState } from "react";

import api from "../services/api";
import type { ContractColumnExpectation, DataContract, UpstreamContractBreach } from "../types/metadata";
import { contractEvaluationBadgeClasses as evaluationBadgeClasses, contractStatusBadgeClasses as statusBadgeClasses } from "../utils/badgeStyles";

type Props = {
  datasetId: string;
  canEdit: boolean;
};

const EMPTY_ROW: ContractColumnExpectation = {
  name: "",
  data_type: "",
  nullable: undefined,
  required: true,
};

export default function DataContractPanel({ datasetId, canEdit }: Props) {
  const [contracts, setContracts] = useState<DataContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [owner, setOwner] = useState("");
  const [minOverallScore, setMinOverallScore] = useState("");
  const [rows, setRows] = useState<ContractColumnExpectation[]>([{ ...EMPTY_ROW }]);
  const [saving, setSaving] = useState(false);

  const [upstreamBreaches, setUpstreamBreaches] = useState<UpstreamContractBreach[]>([]);

  useEffect(() => {
    async function fetchContracts() {
      try {
        setErrorMessage(null);
        const response = await api.get<DataContract[]>(
          `/api/data-contracts/dataset/${datasetId}`
        );
        setContracts(response.data);
      } catch (error) {
        console.error(error);
        setErrorMessage("Unable to load contracts right now.");
      } finally {
        setLoading(false);
      }
    }

    async function fetchUpstreamBreaches() {
      try {
        const response = await api.get<UpstreamContractBreach[]>(
          `/api/data-contracts/dataset/${datasetId}/upstream-breaches`
        );
        setUpstreamBreaches(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    if (!datasetId) return;
    fetchContracts();
    fetchUpstreamBreaches();
  }, [datasetId]);

  function updateRow(index: number, field: keyof ContractColumnExpectation, value: string | boolean | undefined) {
    setRows((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  }

  function addRow() {
    setRows((prev) => [...prev, { ...EMPTY_ROW }]);
  }

  function removeRow(index: number) {
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function createContract() {
    const columns = rows
      .filter((row) => row.name.trim() !== "")
      .map((row) => ({
        name: row.name.trim(),
        data_type: row.data_type?.trim() || undefined,
        nullable: row.nullable,
        required: row.required,
      }));

    const trimmedScore = minOverallScore.trim();
    const parsedScore = trimmedScore === "" ? undefined : Number(trimmedScore);

    if (columns.length === 0 && parsedScore === undefined) {
      alert("Add at least one column expectation or a minimum quality score");
      return;
    }

    try {
      setSaving(true);
      await api.post("/api/data-contracts", {
        dataset_id: datasetId,
        owner: owner || undefined,
        schema_expectations: { columns },
        quality_thresholds:
          parsedScore !== undefined ? { min_overall_score: parsedScore } : undefined,
      });
      window.location.reload();
    } catch (error) {
      console.error(error);
      alert("Failed to create contract");
    } finally {
      setSaving(false);
    }
  }

  async function activateContract(contractId: string) {
    try {
      await api.post(`/api/data-contracts/${contractId}/activate`);
      window.location.reload();
    } catch (error) {
      console.error(error);
      alert("Failed to activate contract");
    }
  }

  async function deprecateContract(contractId: string) {
    try {
      await api.post(`/api/data-contracts/${contractId}/deprecate`);
      window.location.reload();
    } catch (error) {
      console.error(error);
      alert("Failed to deprecate contract");
    }
  }

  return (
    <div className="bg-white rounded-xl p-6 shadow">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-semibold">Data Contracts</h2>

        {canEdit && !showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="rounded-lg border px-3 py-2 text-sm hover:bg-gray-50"
          >
            + New Contract
          </button>
        )}
      </div>

      {upstreamBreaches.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3">
          <div className="text-sm font-semibold text-amber-800">
            ⚠ {upstreamBreaches.length} upstream dataset{upstreamBreaches.length === 1 ? "" : "s"} with a breached contract
          </div>
          <div className="mt-1 text-xs text-amber-700">
            This dataset&apos;s own contract may be fine, but data feeding into it isn&apos;t:
          </div>
          <ul className="mt-2 space-y-1">
            {upstreamBreaches.map((breach) => (
              <li key={breach.contract_id} className="text-xs text-amber-800">
                <span className="font-mono">{breach.schema_name}.{breach.dataset_name}</span>
                {" "}(contract v{breach.contract_version})
                {breach.breach_details ? `: ${breach.breach_details}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {loading && <div className="text-gray-500">Loading contracts...</div>}

      {errorMessage && <div className="text-red-600">{errorMessage}</div>}

      {!loading && !errorMessage && contracts.length === 0 && !showForm && (
        <div className="text-gray-500 text-sm">
          No contract has been defined for this dataset yet. Contracts are opt-in -
          a steward declares the expected schema, and every scan or upload is
          checked against it automatically.
        </div>
      )}

      {contracts.length > 0 && (
        <div className="space-y-3 mb-4">
          {contracts.map((contract) => (
            <div key={contract.id} className="border rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">v{contract.version}</span>
                  <span
                    className={`text-xs px-2 py-1 rounded-full ${statusBadgeClasses(contract.status)}`}
                  >
                    {contract.status}
                  </span>
                  <span
                    className={`text-xs px-2 py-1 rounded-full ${evaluationBadgeClasses(contract.last_status)}`}
                  >
                    {contract.last_status || "NOT YET EVALUATED"}
                  </span>
                </div>

                {canEdit && contract.status === "DRAFT" && (
                  <button
                    onClick={() => activateContract(contract.id)}
                    className="text-sm rounded-lg bg-black px-3 py-1 text-white hover:bg-gray-800"
                  >
                    Activate
                  </button>
                )}

                {canEdit && contract.status === "ACTIVE" && (
                  <button
                    onClick={() => deprecateContract(contract.id)}
                    className="text-sm rounded-lg border px-3 py-1 hover:bg-gray-50"
                  >
                    Deprecate
                  </button>
                )}
              </div>

              {contract.owner && (
                <div className="text-sm text-gray-500 mt-2">Owner: {contract.owner}</div>
              )}

              {contract.schema_expectations.columns.length > 0 && (
                <div className="text-sm text-gray-500 mt-2">
                  {contract.schema_expectations.columns.length} column expectation
                  {contract.schema_expectations.columns.length === 1 ? "" : "s"}:{" "}
                  {contract.schema_expectations.columns.map((c) => c.name).join(", ")}
                </div>
              )}

              {contract.quality_thresholds?.min_overall_score !== undefined &&
                contract.quality_thresholds?.min_overall_score !== null && (
                  <div className="text-sm text-gray-500 mt-1">
                    Minimum data quality score: {String(contract.quality_thresholds.min_overall_score)}
                  </div>
                )}

              {contract.last_status === "BREACHED" && contract.last_breach_details && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2 mt-2">
                  {contract.last_breach_details}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {canEdit && showForm && (
        <div className="border-t pt-4">
          <div className="mb-4 grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-gray-500 block mb-1">Owner</label>
              <input
                type="text"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                placeholder="e.g. Data Platform Team"
                value={owner}
                onChange={(event) => setOwner(event.target.value)}
              />
            </div>
            <div>
              <label className="text-sm text-gray-500 block mb-1">
                Minimum data quality score (optional)
              </label>
              <input
                type="number"
                min={0}
                max={100}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                placeholder="e.g. 90"
                value={minOverallScore}
                onChange={(event) => setMinOverallScore(event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2 mb-3">
            {rows.map((row, index) => (
              <div key={index} className="grid grid-cols-12 gap-2 items-center">
                <input
                  placeholder="Column name"
                  className="col-span-4 rounded-lg border px-2 py-1 text-sm"
                  value={row.name}
                  onChange={(event) => updateRow(index, "name", event.target.value)}
                />
                <input
                  placeholder="Type (optional)"
                  className="col-span-3 rounded-lg border px-2 py-1 text-sm"
                  value={row.data_type ?? ""}
                  onChange={(event) => updateRow(index, "data_type", event.target.value)}
                />
                <label className="col-span-2 flex items-center gap-1 text-xs text-gray-600">
                  <input
                    type="checkbox"
                    checked={row.nullable === false}
                    onChange={(event) =>
                      updateRow(index, "nullable", event.target.checked ? false : undefined)
                    }
                  />
                  NOT NULL
                </label>
                <label className="col-span-2 flex items-center gap-1 text-xs text-gray-600">
                  <input
                    type="checkbox"
                    checked={row.required}
                    onChange={(event) => updateRow(index, "required", event.target.checked)}
                  />
                  Required
                </label>
                <button
                  onClick={() => removeRow(index)}
                  className="col-span-1 text-red-600 text-sm"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={addRow}
              className="rounded-lg border px-3 py-2 text-sm hover:bg-gray-50"
            >
              + Add Column
            </button>
            <button
              onClick={createContract}
              disabled={saving}
              className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save Draft"}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="text-sm text-gray-500"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
