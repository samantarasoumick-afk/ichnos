"use client";

import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type { AuditLogEntry } from "../../types/metadata";

type Filters = {
  action: string;
  actor: string;
  resource_type: string;
  date_from: string;
  date_to: string;
};

const EMPTY_FILTERS: Filters = {
  action: "",
  actor: "",
  resource_type: "",
  date_from: "",
  date_to: "",
};

function toQueryParams(filters: Filters) {
  const params: Record<string, string> = {};
  if (filters.action.trim()) params.action = filters.action.trim();
  if (filters.actor.trim()) params.actor = filters.actor.trim();
  if (filters.resource_type.trim()) params.resource_type = filters.resource_type.trim();
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  return params;
}

export default function AuditLogPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);

  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const filtersActive =
    appliedFilters.action !== "" ||
    appliedFilters.actor !== "" ||
    appliedFilters.resource_type !== "" ||
    appliedFilters.date_from !== "" ||
    appliedFilters.date_to !== "";

  useEffect(() => {
    if (!user) return;

    async function fetchAuditLog() {
      try {
        setLoading(true);
        setErrorMessage(null);
        const response = await api.get<AuditLogEntry[]>("/api/audit-log", {
          params: toQueryParams(appliedFilters),
        });
        setEntries(response.data);
      } catch (error) {
        console.error(error);
        setErrorMessage(
          "Unable to load the audit log. Please make sure the backend is running."
        );
      } finally {
        setLoading(false);
      }
    }

    fetchAuditLog();
  }, [user, appliedFilters]);

  function applyFilters() {
    setAppliedFilters(filters);
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
  }

  async function handleDownload() {
    setDownloading(true);
    setDownloadError(null);

    try {
      const response = await api.get("/api/audit-log/export", {
        params: toQueryParams(appliedFilters),
        responseType: "blob",
      });

      const url = window.URL.createObjectURL(
        new Blob([response.data], { type: "text/csv" })
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error(error);
      setDownloadError("Unable to export the audit log right now.");
    } finally {
      setDownloading(false);
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

      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold">Audit Log</h1>
          <div className="mt-2 text-gray-600">
            Append-only record of who did what, across your organization.
          </div>
        </div>

        <button
          onClick={handleDownload}
          disabled={downloading}
          className="shrink-0 rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
        >
          {downloading ? "Exporting..." : "Download CSV"}
        </button>
      </div>

      {downloadError && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {downloadError}
        </div>
      )}

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      <div className="mb-6 rounded-xl bg-white p-6 shadow">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <input
            type="text"
            placeholder="Action (e.g. source.create)"
            className="rounded-lg border px-3 py-2 text-sm"
            value={filters.action}
            onChange={(event) => setFilters((prev) => ({ ...prev, action: event.target.value }))}
          />
          <input
            type="text"
            placeholder="Actor email"
            className="rounded-lg border px-3 py-2 text-sm"
            value={filters.actor}
            onChange={(event) => setFilters((prev) => ({ ...prev, actor: event.target.value }))}
          />
          <input
            type="text"
            placeholder="Resource type"
            className="rounded-lg border px-3 py-2 text-sm"
            value={filters.resource_type}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, resource_type: event.target.value }))
            }
          />
          <input
            type="date"
            className="rounded-lg border px-3 py-2 text-sm"
            value={filters.date_from}
            onChange={(event) => setFilters((prev) => ({ ...prev, date_from: event.target.value }))}
          />
          <input
            type="date"
            className="rounded-lg border px-3 py-2 text-sm"
            value={filters.date_to}
            onChange={(event) => setFilters((prev) => ({ ...prev, date_to: event.target.value }))}
          />
        </div>

        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={applyFilters}
            className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800"
          >
            Apply Filters
          </button>
          {filtersActive && (
            <button
              onClick={clearFilters}
              className="rounded-lg border px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Clear Filters
            </button>
          )}
        </div>
      </div>

      <section className="rounded-xl bg-white p-6 shadow">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-3">When</th>
                <th className="py-3">Actor</th>
                <th className="py-3">Action</th>
                <th className="py-3">Resource</th>
                <th className="py-3">Details</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="border-b hover:bg-gray-50">
                  <td className="py-3 whitespace-nowrap text-gray-500">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="py-3">{entry.actor_email || "System"}</td>
                  <td className="py-3">
                    <span className="rounded-full bg-gray-100 px-2 py-1 text-xs font-medium">
                      {entry.action}
                    </span>
                  </td>
                  <td className="py-3 text-gray-600">
                    {entry.resource_type
                      ? `${entry.resource_type}${
                          entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ""
                        }`
                      : "-"}
                  </td>
                  <td className="py-3 text-gray-600">{entry.details || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && entries.length === 0 && (
          <div className="py-8 text-gray-500">
            {filtersActive
              ? "No audit events match these filters."
              : "No audit events recorded yet."}
          </div>
        )}
      </section>
    </main>
  );
}
