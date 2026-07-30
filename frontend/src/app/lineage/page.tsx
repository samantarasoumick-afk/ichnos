"use client";

import { useEffect, useState } from "react";

import CreateLineageForm from "../../components/CreateLineageForm";
import LineageEdgeCard from "../../components/LineageEdgeCard";
import LineageGraph from "../../components/LineageGraph";
import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type {
  Dataset,
  Lineage,
} from "../../types/metadata";

function datasetLabel(dataset: Dataset) {
  return `${dataset.schema_name}.${dataset.name}`;
}

export default function LineagePage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [lineage, setLineage] = useState<Lineage[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Deep-linkable from the guided tour (?dataset=<id>) - same
  // window.location.search read pattern DiscussionsPage uses, so this
  // stays a plain client-side filter rather than needing a Suspense
  // boundary for useSearchParams().
  const [selectedDatasetId, setSelectedDatasetId] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("dataset") ?? "";
  });
  const [dependencies, setDependencies] = useState<Lineage[]>([]);
  const [impact, setImpact] = useState<Lineage[]>([]);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);

  const [datasetSearch, setDatasetSearch] = useState("");
  const [isDatasetDropdownOpen, setIsDatasetDropdownOpen] = useState(false);

  useEffect(() => {
    if (!user) return;

    async function fetchLineage() {
      try {
        setErrorMessage(null);

        const [
          datasetResponse,
          lineageResponse,
        ] = await Promise.all([
          api.get<Dataset[]>("/api/datasets"),
          api.get<Lineage[]>("/api/lineage"),
        ]);

        setDatasets(datasetResponse.data);
        setLineage(lineageResponse.data);
      } catch (error) {
        console.error(error);
        setErrorMessage(
          "Unable to load lineage. Please make sure the backend is running on http://127.0.0.1:8000."
        );
      } finally {
        setLoading(false);
      }
    }

    fetchLineage();
  }, [user]);

  useEffect(() => {
    if (!selectedDatasetId) {
      return;
    }

    async function fetchImpactAndDependencies() {
      try {
        setLookupLoading(true);
        setLookupError(null);

        const [dependenciesResponse, impactResponse] = await Promise.all([
          api.get<Lineage[]>(`/api/lineage/${selectedDatasetId}/dependencies`),
          api.get<Lineage[]>(`/api/lineage/${selectedDatasetId}/impact`),
        ]);

        setDependencies(dependenciesResponse.data);
        setImpact(impactResponse.data);
      } catch (error) {
        console.error(error);
        setLookupError("Unable to load impact analysis for this dataset.");
      } finally {
        setLookupLoading(false);
      }
    }

    fetchImpactAndDependencies();
  }, [selectedDatasetId]);

  const datasetById = new Map(datasets.map((dataset) => [dataset.id, dataset]));

  function otherDatasetLabel(edge: Lineage, direction: "upstream" | "downstream") {
    const id = direction === "upstream" ? edge.upstream_dataset_id : edge.downstream_dataset_id;
    const dataset = datasetById.get(id);
    return dataset ? datasetLabel(dataset) : id;
  }

  function selectDataset(dataset: Dataset) {
    setSelectedDatasetId(dataset.id);
    setDatasetSearch(datasetLabel(dataset));
    setIsDatasetDropdownOpen(false);
  }

  function clearDatasetSelection() {
    setSelectedDatasetId("");
    setDatasetSearch("");
    setDependencies([]);
    setImpact([]);
  }

  const sortedDatasets = datasets
    .slice()
    .sort((a, b) => datasetLabel(a).localeCompare(datasetLabel(b)));

  const filteredDatasetOptions = sortedDatasets.filter((dataset) =>
    datasetLabel(dataset).toLowerCase().includes(datasetSearch.trim().toLowerCase())
  );

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  const canEdit = user.role === "admin" || user.role === "steward";

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-8">
        <h1 className="text-4xl font-bold">
          Lineage
        </h1>
        <p className="mt-2 text-gray-600">
          Upstream and downstream dataset relationships, and what breaks if a dataset changes.
        </p>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {loading && (
        <div className="rounded-xl bg-white p-6 shadow">
          Loading lineage...
        </div>
      )}

      {!loading && !errorMessage && canEdit && (
        <CreateLineageForm datasets={datasets} />
      )}

      {!loading && !errorMessage && (
        <div className="mb-8 rounded-xl bg-white p-6 shadow">
          <h2 className="mb-4 text-xl font-semibold">Impact Analysis</h2>

          <div className="relative mb-4 w-full max-w-md">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search for a dataset..."
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={datasetSearch}
                onFocus={() => setIsDatasetDropdownOpen(true)}
                onChange={(event) => {
                  setDatasetSearch(event.target.value);
                  setIsDatasetDropdownOpen(true);
                }}
                onBlur={() => {
                  // Delay so a click on an option registers before the
                  // dropdown closes (blur fires before click otherwise).
                  setTimeout(() => setIsDatasetDropdownOpen(false), 150);
                }}
              />
              {selectedDatasetId && (
                <button
                  type="button"
                  onClick={clearDatasetSelection}
                  className="shrink-0 rounded-lg border px-3 py-2 text-xs text-gray-500 hover:bg-gray-50"
                >
                  Clear
                </button>
              )}
            </div>

            {isDatasetDropdownOpen && (
              <div className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border bg-white shadow-lg">
                {filteredDatasetOptions.length === 0 && (
                  <div className="px-3 py-2 text-sm text-gray-500">No datasets match.</div>
                )}
                {filteredDatasetOptions.map((dataset) => (
                  <button
                    type="button"
                    key={dataset.id}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => selectDataset(dataset)}
                    className={`block w-full px-3 py-2 text-left text-sm hover:bg-gray-50 ${
                      dataset.id === selectedDatasetId ? "bg-gray-50 font-semibold" : ""
                    }`}
                  >
                    {datasetLabel(dataset)}
                  </button>
                ))}
              </div>
            )}
          </div>

          {lookupLoading && <div className="text-gray-500">Loading...</div>}
          {lookupError && <div className="text-red-600">{lookupError}</div>}

          {selectedDatasetId && !lookupLoading && !lookupError && (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-semibold text-gray-500">
                  Depends on (upstream)
                </h3>
                <div className="space-y-2">
                  {dependencies.map((edge) => (
                    <LineageEdgeCard
                      key={edge.id}
                      edge={edge}
                      href={`/datasets/${edge.upstream_dataset_id}`}
                      label={otherDatasetLabel(edge, "upstream")}
                      canEdit={canEdit}
                    />
                  ))}
                  {dependencies.length === 0 && (
                    <div className="text-sm text-gray-500">
                      Nothing upstream of this dataset.
                    </div>
                  )}
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold text-gray-500">
                  Would be affected (downstream)
                </h3>
                <div className="space-y-2">
                  {impact.map((edge) => (
                    <LineageEdgeCard
                      key={edge.id}
                      edge={edge}
                      href={`/datasets/${edge.downstream_dataset_id}`}
                      label={otherDatasetLabel(edge, "downstream")}
                      canEdit={canEdit}
                    />
                  ))}
                  {impact.length === 0 && (
                    <div className="text-sm text-gray-500">
                      Nothing downstream of this dataset.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && !errorMessage && lineage.length === 0 && (
        <div className="rounded-xl bg-white p-6 shadow">
          No lineage relationships have been registered yet.
        </div>
      )}

      {!loading && !errorMessage && lineage.length > 0 && (
        <LineageGraph
          datasets={datasets}
          lineage={lineage}
        />
      )}
    </main>
  );
}
