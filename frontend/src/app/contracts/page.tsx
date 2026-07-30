"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type { DataContract, Dataset } from "../../types/metadata";

type StatusFilter = "ALL" | "ACTIVE" | "BREACHED" | "COMPLIANT" | "DRAFT" | "DEPRECATED";

const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "ACTIVE", label: "Active" },
  { key: "BREACHED", label: "Breached" },
  { key: "COMPLIANT", label: "Compliant" },
  { key: "DRAFT", label: "Draft" },
  { key: "DEPRECATED", label: "Deprecated" },
];

function statusBadgeClasses(status: string) {
  if (status === "ACTIVE") return "bg-blue-100 text-blue-700";
  if (status === "DEPRECATED") return "bg-gray-100 text-gray-500";
  return "bg-yellow-100 text-yellow-700"; // DRAFT
}

function evaluationBadgeClasses(status: string | null | undefined) {
  if (status === "COMPLIANT") return "bg-green-100 text-green-700";
  if (status === "BREACHED") return "bg-red-100 text-red-700";
  return "bg-gray-100 text-gray-500"; // not yet evaluated
}

export default function ContractsPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [contracts, setContracts] = useState<DataContract[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [busyContractId, setBusyContractId] = useState<string | null>(null);

  const canEdit = user?.role === "admin" || user?.role === "steward" || user?.role === "data_owner";

  async function loadContracts() {
    try {
      const response = await api.get<DataContract[]>("/api/data-contracts");
      setContracts(response.data);
    } catch (error) {
      console.error(error);
      setErrorMessage("Unable to load contracts. Please make sure the backend is running.");
    }
  }

  useEffect(() => {
    if (!user) return;

    async function loadAll() {
      setLoading(true);
      await Promise.all([
        loadContracts(),
        (async () => {
          try {
            const response = await api.get<Dataset[]>("/api/datasets");
            setDatasets(response.data);
          } catch (error) {
            console.error(error);
          }
        })(),
      ]);
      setLoading(false);
    }

    loadAll();
  }, [user]);

  const datasetById = useMemo(() => new Map(datasets.map((d) => [d.id, d])), [datasets]);

  const rows = useMemo(() => {
    const trimmed = search.trim().toLowerCase();

    return contracts
      .map((contract) => ({ contract, dataset: datasetById.get(contract.dataset_id) }))
      .filter(({ contract, dataset }) => {
        if (statusFilter === "ACTIVE" && contract.status !== "ACTIVE") return false;
        if (statusFilter === "DRAFT" && contract.status !== "DRAFT") return false;
        if (statusFilter === "DEPRECATED" && contract.status !== "DEPRECATED") return false;
        if (statusFilter === "BREACHED" && contract.last_status !== "BREACHED") return false;
        if (statusFilter === "COMPLIANT" && contract.last_status !== "COMPLIANT") return false;

        if (!trimmed) return true;
        const haystack = `${dataset?.schema_name ?? ""}.${dataset?.name ?? ""} ${contract.owner ?? ""}`.toLowerCase();
        return haystack.includes(trimmed);
      })
      .sort((a, b) => {
        const labelA = a.dataset ? `${a.dataset.schema_name}.${a.dataset.name}` : "";
        const labelB = b.dataset ? `${b.dataset.schema_name}.${b.dataset.name}` : "";
        return labelA.localeCompare(labelB);
      });
  }, [contracts, datasetById, search, statusFilter]);

  const counts = useMemo(() => {
    return {
      active: contracts.filter((c) => c.status === "ACTIVE").length,
      breached: contracts.filter((c) => c.last_status === "BREACHED").length,
      compliant: contracts.filter((c) => c.last_status === "COMPLIANT").length,
    };
  }, [contracts]);

  async function activateContract(contractId: string) {
    setBusyContractId(contractId);
    try {
      await api.post(`/api/data-contracts/${contractId}/activate`);
      await loadContracts();
    } catch (error) {
      console.error(error);
      alert("Failed to activate contract");
    } finally {
      setBusyContractId(null);
    }
  }

  async function deprecateContract(contractId: string) {
    setBusyContractId(contractId);
    try {
      await api.post(`/api/data-contracts/${contractId}/deprecate`);
      await loadContracts();
    } catch (error) {
      console.error(error);
      alert("Failed to deprecate contract");
    } finally {
      setBusyContractId(null);
    }
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-lg bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-6">
        <h1 className="text-4xl font-bold">Contracts</h1>
        <p className="mt-2 max-w-2xl text-gray-600">
          Every data contract across the catalog in one place - search by dataset, and filter down to what&apos;s
          active versus what&apos;s currently breached. Each contract still lives on its own dataset page for
          full editing; this is the org-wide view for triage.
        </p>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">{errorMessage}</div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="mb-4 flex flex-wrap gap-6 rounded-xl bg-white p-4 text-sm text-gray-600 shadow">
            <span><strong className="text-gray-900">{contracts.length}</strong> total contracts</span>
            <span><strong className="text-blue-700">{counts.active}</strong> active</span>
            <span><strong className="text-red-700">{counts.breached}</strong> breached</span>
            <span><strong className="text-green-700">{counts.compliant}</strong> compliant</span>
          </div>

          <div className="mb-6 flex flex-wrap items-center gap-3">
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by dataset or owner..."
              className="w-full max-w-sm rounded-lg border px-3 py-2 text-sm"
            />
            <div className="flex flex-wrap gap-2">
              {STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  onClick={() => setStatusFilter(filter.key)}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${
                    statusFilter === filter.key ? "border-black bg-black text-white" : "text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-hidden rounded-xl bg-white shadow">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">Dataset</th>
                  <th className="px-4 py-3">Version</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Evaluation</th>
                  <th className="px-4 py-3">Owner</th>
                  <th className="px-4 py-3">Last evaluated</th>
                  {canEdit && <th className="px-4 py-3 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map(({ contract, dataset }) => (
                  <tr key={contract.id} className="border-b last:border-b-0 hover:bg-gray-50">
                    <td className="px-4 py-3">
                      {dataset ? (
                        <Link href={`/datasets/${dataset.id}`} className="font-medium text-gray-900 hover:underline">
                          {dataset.schema_name}.{dataset.name}
                        </Link>
                      ) : (
                        <span className="text-gray-400">Unknown dataset</span>
                      )}
                    </td>
                    <td className="px-4 py-3">v{contract.version}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClasses(contract.status)}`}>
                        {contract.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${evaluationBadgeClasses(contract.last_status)}`}>
                        {contract.last_status || "NOT YET EVALUATED"}
                      </span>
                      {contract.last_status === "BREACHED" && contract.last_breach_details && (
                        <div className="mt-1 max-w-xs text-xs text-red-700">{contract.last_breach_details}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{contract.owner || "–"}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {contract.last_evaluated_at ? new Date(contract.last_evaluated_at).toLocaleString() : "–"}
                    </td>
                    {canEdit && (
                      <td className="px-4 py-3 text-right">
                        {contract.status === "DRAFT" && (
                          <button
                            onClick={() => activateContract(contract.id)}
                            disabled={busyContractId === contract.id}
                            className="rounded-lg bg-black px-3 py-1 text-xs text-white hover:bg-gray-800 disabled:opacity-50"
                          >
                            Activate
                          </button>
                        )}
                        {contract.status === "ACTIVE" && (
                          <button
                            onClick={() => deprecateContract(contract.id)}
                            disabled={busyContractId === contract.id}
                            className="rounded-lg border px-3 py-1 text-xs hover:bg-gray-50 disabled:opacity-50"
                          >
                            Deprecate
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}

                {rows.length === 0 && (
                  <tr>
                    <td colSpan={canEdit ? 7 : 6} className="px-4 py-8 text-center text-gray-500">
                      {contracts.length === 0
                        ? "No data contracts yet - create one from any dataset's detail page."
                        : "No contracts match this search/filter."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
