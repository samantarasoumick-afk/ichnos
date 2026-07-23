"use client";

import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type { Dataset, DatasetColumn } from "../../types/metadata";
import Link from "next/link";

export default function ReferenceDataPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [columnsByDataset, setColumnsByDataset] = useState<Record<string, DatasetColumn[]>>({});
  const [columnsLoading, setColumnsLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    async function fetchDatasets() {
      try {
        setErrorMessage(null);
        const response = await api.get<Dataset[]>("/api/datasets");
        setDatasets(response.data);
      } catch (error) {
        console.error(error);
        setErrorMessage("Unable to load the catalog right now.");
      } finally {
        setLoading(false);
      }
    }

    fetchDatasets();
  }, [user]);

  const referenceDatasets = datasets
    .filter((dataset) => dataset.data_category === "REFERENCE")
    .sort((a, b) => `${a.schema_name}.${a.name}`.localeCompare(`${b.schema_name}.${b.name}`));

  async function toggleExpanded(dataset: Dataset) {
    if (expandedId === dataset.id) {
      setExpandedId(null);
      return;
    }

    setExpandedId(dataset.id);

    if (!columnsByDataset[dataset.id]) {
      setColumnsLoading(dataset.id);
      try {
        const response = await api.get<DatasetColumn[]>(`/api/columns/dataset/${dataset.id}`);
        setColumnsByDataset((prev) => ({ ...prev, [dataset.id]: response.data }));
      } catch (error) {
        console.error(error);
      } finally {
        setColumnsLoading(null);
      }
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

      <div className="mb-8">
        <h1 className="text-4xl font-bold">Reference Data Repository</h1>
        <div className="mt-2 text-gray-600">
          The controlled vocabularies and lookup tables other datasets point
          into - codes, statuses, categories, and similar static reference
          data, auto-classified from the catalog.
        </div>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {!loading && referenceDatasets.length === 0 && !errorMessage && (
        <div className="rounded-xl bg-white p-6 shadow text-gray-500">
          No datasets have been classified as Reference Data yet. Datasets are
          auto-classified when they&rsquo;re first scanned or uploaded - a
          steward can also set or correct a dataset&rsquo;s Data Category
          from its Governance tab.
        </div>
      )}

      <div className="space-y-4">
        {referenceDatasets.map((dataset) => {
          const isExpanded = expandedId === dataset.id;
          const columns = columnsByDataset[dataset.id];

          return (
            <div key={dataset.id} className="rounded-xl bg-white p-6 shadow">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <Link
                    href={`/datasets/${dataset.id}`}
                    className="text-lg font-semibold hover:underline"
                  >
                    {dataset.schema_name}.{dataset.name}
                  </Link>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                    <span>Owner: {dataset.owner || "Not set"}</span>
                    <span>&middot;</span>
                    <span>Steward: {dataset.steward || "Not set"}</span>
                    {dataset.domain && (
                      <>
                        <span>&middot;</span>
                        <span>{dataset.domain}</span>
                      </>
                    )}
                  </div>
                  {dataset.description && (
                    <div className="mt-2 text-sm text-gray-600">{dataset.description}</div>
                  )}
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {dataset.certification === "VERIFIED" && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                      Verified
                    </span>
                  )}
                  <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
                    {dataset.total_columns || 0} columns
                  </span>
                  <button
                    onClick={() => toggleExpanded(dataset)}
                    className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50"
                  >
                    {isExpanded ? "Hide columns" : "Show columns"}
                  </button>
                </div>
              </div>

              {isExpanded && (
                <div className="mt-4 border-t pt-4">
                  {columnsLoading === dataset.id && (
                    <div className="text-sm text-gray-500">Loading columns...</div>
                  )}

                  {columns && columns.length === 0 && (
                    <div className="text-sm text-gray-500">No columns recorded.</div>
                  )}

                  {columns && columns.length > 0 && (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-gray-500">
                          <th className="py-2">Column</th>
                          <th className="py-2">Type</th>
                          <th className="py-2">Nullable</th>
                        </tr>
                      </thead>
                      <tbody>
                        {columns.map((column) => (
                          <tr key={column.id} className="border-b last:border-0">
                            <td className="py-2 font-medium">{column.name}</td>
                            <td className="py-2 text-gray-600">{column.data_type}</td>
                            <td className="py-2 text-gray-600">
                              {column.nullable ? "Yes" : "No"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </main>
  );
}
