"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type {
  BusinessProcess,
  BusinessProcessCreate,
  BusinessProcessDatasetSummary,
  BusinessProcessUpdate,
} from "../../types/metadata";

const EMPTY_NEW_PROCESS: BusinessProcessCreate = {
  name: "",
  description: "",
  narrative: "",
  owner: "",
};

const DATA_CATEGORY_GROUPS: { key: string; label: string; badgeClasses: string }[] = [
  { key: "MASTER", label: "Master data", badgeClasses: "bg-purple-100 text-purple-700" },
  { key: "REFERENCE", label: "Reference data", badgeClasses: "bg-blue-100 text-blue-700" },
  { key: "TRANSACTIONAL", label: "Transactional data", badgeClasses: "bg-amber-100 text-amber-700" },
  { key: "ANALYTICAL", label: "Analytical data", badgeClasses: "bg-green-100 text-green-700" },
  { key: "UNCATEGORIZED", label: "Not yet classified", badgeClasses: "bg-gray-100 text-gray-600" },
];

function groupDatasetsByCategory(datasets: BusinessProcessDatasetSummary[]) {
  const groups: Record<string, BusinessProcessDatasetSummary[]> = {};
  for (const dataset of datasets) {
    const key = dataset.data_category || "UNCATEGORIZED";
    if (!groups[key]) groups[key] = [];
    groups[key].push(dataset);
  }
  return groups;
}

export default function ProcessesPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [processes, setProcesses] = useState<BusinessProcess[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canEditProcesses = user?.role === "admin" || user?.role === "steward";

  const [showNewProcessForm, setShowNewProcessForm] = useState(false);
  const [newProcess, setNewProcess] = useState<BusinessProcessCreate>(EMPTY_NEW_PROCESS);
  const [creatingProcess, setCreatingProcess] = useState(false);
  const [createProcessError, setCreateProcessError] = useState<string | null>(null);

  const [editingProcessId, setEditingProcessId] = useState<string | null>(null);
  const [editProcessForm, setEditProcessForm] = useState<BusinessProcessUpdate>({});
  const [savingProcess, setSavingProcess] = useState(false);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [datasetsByProcess, setDatasetsByProcess] = useState<
    Record<string, BusinessProcessDatasetSummary[]>
  >({});
  const [datasetsLoading, setDatasetsLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    async function fetchProcesses() {
      try {
        setErrorMessage(null);
        const response = await api.get<BusinessProcess[]>("/api/business-processes");
        setProcesses(
          [...response.data].sort((a, b) => a.name.localeCompare(b.name))
        );
      } catch (error) {
        console.error(error);
        setErrorMessage(
          "Unable to load business processes. Please make sure the backend is running."
        );
      }
    }

    fetchProcesses();
  }, [user]);

  async function handleCreateProcess() {
    if (!newProcess.name.trim()) {
      setCreateProcessError("Name is required.");
      return;
    }

    setCreatingProcess(true);
    setCreateProcessError(null);

    try {
      const response = await api.post<BusinessProcess>("/api/business-processes", {
        name: newProcess.name.trim(),
        description: newProcess.description || null,
        narrative: newProcess.narrative || null,
        owner: newProcess.owner || null,
      });
      setProcesses((prev) =>
        [...prev, response.data].sort((a, b) => a.name.localeCompare(b.name))
      );
      setNewProcess(EMPTY_NEW_PROCESS);
      setShowNewProcessForm(false);
    } catch (error) {
      console.error(error);
      setCreateProcessError("Unable to create process. It may already exist.");
    } finally {
      setCreatingProcess(false);
    }
  }

  function startEditingProcess(process: BusinessProcess) {
    setEditingProcessId(process.id);
    setEditProcessForm({
      name: process.name,
      description: process.description || "",
      narrative: process.narrative || "",
      owner: process.owner || "",
    });
  }

  async function handleSaveProcess(processId: string) {
    setSavingProcess(true);

    try {
      const response = await api.patch<BusinessProcess>(
        `/api/business-processes/${processId}`,
        {
          name: editProcessForm.name,
          description: editProcessForm.description || null,
          narrative: editProcessForm.narrative || null,
          owner: editProcessForm.owner || null,
        }
      );
      setProcesses((prev) =>
        prev.map((process) => (process.id === processId ? response.data : process))
      );
      setEditingProcessId(null);
    } catch (error) {
      console.error(error);
    } finally {
      setSavingProcess(false);
    }
  }

  async function toggleExpanded(process: BusinessProcess) {
    if (expandedId === process.id) {
      setExpandedId(null);
      return;
    }

    setExpandedId(process.id);

    if (!datasetsByProcess[process.id]) {
      setDatasetsLoading(process.id);
      try {
        const response = await api.get<BusinessProcessDatasetSummary[]>(
          `/api/business-processes/${process.id}/datasets`
        );
        setDatasetsByProcess((prev) => ({ ...prev, [process.id]: response.data }));
      } catch (error) {
        console.error(error);
      } finally {
        setDatasetsLoading(null);
      }
    }
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold">Process Repository</h1>
          <div className="mt-2 max-w-2xl text-gray-600">
            The &quot;process dimension&quot; - which end-to-end business
            activity each dataset supports (Order-to-Cash, Lead-to-Opportunity,
            and so on), independent of team or domain.
          </div>
        </div>
        {canEditProcesses && (
          <button
            onClick={() => setShowNewProcessForm((prev) => !prev)}
            className="shrink-0 rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800"
          >
            {showNewProcessForm ? "Cancel" : "New Process"}
          </button>
        )}
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {showNewProcessForm && (
        <div className="mb-6 space-y-3 rounded-xl bg-white p-6 shadow">
          <input
            type="text"
            placeholder="Name (e.g. Order-to-Cash)"
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={newProcess.name}
            onChange={(event) =>
              setNewProcess((prev) => ({ ...prev, name: event.target.value }))
            }
          />
          <textarea
            placeholder="Description"
            rows={2}
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={newProcess.description}
            onChange={(event) =>
              setNewProcess((prev) => ({ ...prev, description: event.target.value }))
            }
          />
          <div>
            <textarea
              placeholder={
                "Narrative - how does the data actually flow here? e.g. \"A Customer " +
                "(Master) orders (Transactional) from a Store (Master) in Mumbai (Reference).\""
              }
              rows={2}
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={newProcess.narrative}
              onChange={(event) =>
                setNewProcess((prev) => ({ ...prev, narrative: event.target.value }))
              }
            />
            <div className="mt-1 text-xs text-gray-400">
              Optional. A plain-language story of which Master/Reference data interacts via
              Transactional data, and what Analytical data comes out of it.
            </div>
          </div>
          <input
            type="text"
            placeholder="Owner"
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={newProcess.owner}
            onChange={(event) =>
              setNewProcess((prev) => ({ ...prev, owner: event.target.value }))
            }
          />

          {createProcessError && (
            <div className="text-sm text-red-600">{createProcessError}</div>
          )}

          <button
            onClick={handleCreateProcess}
            disabled={creatingProcess}
            className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {creatingProcess ? "Creating..." : "Create Process"}
          </button>
        </div>
      )}

      <div className="space-y-4">
        {processes.map((process) =>
          editingProcessId === process.id ? (
            <div key={process.id} className="space-y-3 rounded-xl bg-white p-6 shadow">
              <input
                type="text"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={editProcessForm.name ?? ""}
                onChange={(event) =>
                  setEditProcessForm((prev) => ({ ...prev, name: event.target.value }))
                }
              />
              <textarea
                rows={2}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={editProcessForm.description ?? ""}
                onChange={(event) =>
                  setEditProcessForm((prev) => ({ ...prev, description: event.target.value }))
                }
              />
              <textarea
                placeholder="Narrative - how the data actually flows"
                rows={2}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={editProcessForm.narrative ?? ""}
                onChange={(event) =>
                  setEditProcessForm((prev) => ({ ...prev, narrative: event.target.value }))
                }
              />
              <input
                type="text"
                placeholder="Owner"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={editProcessForm.owner ?? ""}
                onChange={(event) =>
                  setEditProcessForm((prev) => ({ ...prev, owner: event.target.value }))
                }
              />

              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleSaveProcess(process.id)}
                  disabled={savingProcess}
                  className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  {savingProcess ? "Saving..." : "Save"}
                </button>
                <button
                  onClick={() => setEditingProcessId(null)}
                  className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-100"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div key={process.id} className="rounded-xl bg-white p-6 shadow">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 text-lg font-semibold">
                    {process.name}
                    {process.is_seed_data && (
                      <span className="rounded-full bg-purple-100 px-1.5 py-0.5 text-[10px] text-purple-700">
                        Demo
                      </span>
                    )}
                  </div>
                  {process.description && (
                    <div className="mt-1 text-sm text-gray-600">{process.description}</div>
                  )}
                  {process.narrative && (
                    <div className="mt-2 rounded-lg bg-gray-50 px-3 py-2 text-sm italic text-gray-700">
                      &ldquo;{process.narrative}&rdquo;
                    </div>
                  )}
                  <div className="mt-3 text-xs text-gray-500">
                    {process.owner || "No owner"} &middot; {process.dataset_count} dataset
                    {process.dataset_count === 1 ? "" : "s"}
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {canEditProcesses && (
                    <button
                      onClick={() => startEditingProcess(process)}
                      className="text-xs text-gray-500 hover:text-black"
                    >
                      Edit
                    </button>
                  )}
                  <button
                    onClick={() => toggleExpanded(process)}
                    className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50"
                  >
                    {expandedId === process.id ? "Hide datasets" : "Show datasets"}
                  </button>
                </div>
              </div>

              {expandedId === process.id && (
                <div className="mt-4 border-t pt-4">
                  {datasetsLoading === process.id && (
                    <div className="text-sm text-gray-500">Loading datasets...</div>
                  )}

                  {datasetsByProcess[process.id]?.length === 0 && (
                    <div className="text-sm text-gray-500">
                      No datasets are linked to this process yet.
                    </div>
                  )}

                  {datasetsByProcess[process.id] && datasetsByProcess[process.id].length > 0 && (
                    <div className="space-y-3">
                      {DATA_CATEGORY_GROUPS.map((group) => {
                        const datasetsInGroup =
                          groupDatasetsByCategory(datasetsByProcess[process.id])[group.key];
                        if (!datasetsInGroup || datasetsInGroup.length === 0) return null;
                        return (
                          <div key={group.key}>
                            <div
                              className={`mb-1.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${group.badgeClasses}`}
                            >
                              {group.label}
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {datasetsInGroup.map((dataset) => (
                                <Link
                                  key={dataset.id}
                                  href={`/datasets/${dataset.id}`}
                                  className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700 hover:bg-gray-200"
                                >
                                  {dataset.schema_name}.{dataset.name}
                                </Link>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        )}

        {processes.length === 0 && !showNewProcessForm && (
          <div className="rounded-xl border border-dashed bg-white p-8 text-center text-gray-500">
            No business processes yet.
            {canEditProcesses
              ? " Click \"New Process\" to add the first one."
              : " Ask an admin or steward to add one."}
          </div>
        )}
      </div>
    </main>
  );
}
