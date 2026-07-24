"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type { DataQuality, Dataset, EffectiveQuality } from "../../types/metadata";

type Row = {
  dataset: Dataset;
  dq: DataQuality | null;
  effective: EffectiveQuality | null;
  score: number | null; // effective score if present, else own overall_score
};

type ThresholdFilter = "ALL" | "BELOW_80" | "BELOW_50" | "UNPROFILED";

const DIMENSIONS: { key: keyof DataQuality; label: string }[] = [
  { key: "completeness", label: "Completeness" },
  { key: "uniqueness", label: "Uniqueness" },
  { key: "validity", label: "Validity" },
  { key: "consistency", label: "Consistency" },
  { key: "freshness", label: "Freshness" },
];

function barColor(value: number) {
  if (value >= 80) return "bg-green-500";
  if (value >= 50) return "bg-yellow-500";
  return "bg-red-500";
}

function scoreBadgeClasses(score: number | null) {
  if (score === null) return "bg-gray-100 text-gray-500";
  if (score >= 80) return "bg-green-100 text-green-700";
  if (score >= 50) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-700";
}

export default function DataQualityPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dqList, setDqList] = useState<DataQuality[]>([]);
  const [effectiveList, setEffectiveList] = useState<EffectiveQuality[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState("ALL");
  const [thresholdFilter, setThresholdFilter] = useState<ThresholdFilter>("ALL");

  useEffect(() => {
    if (!user) return;

    async function loadAll() {
      setLoading(true);
      try {
        const [datasetsRes, dqRes, effectiveRes] = await Promise.all([
          api.get<Dataset[]>("/api/datasets"),
          api.get<DataQuality[]>("/api/data-quality"),
          api.get<EffectiveQuality[]>("/api/data-quality/effective"),
        ]);
        setDatasets(datasetsRes.data);
        setDqList(dqRes.data);
        setEffectiveList(effectiveRes.data);
      } catch (error) {
        console.error(error);
        setErrorMessage("Unable to load data quality data. Please make sure the backend is running.");
      } finally {
        setLoading(false);
      }
    }

    loadAll();
  }, [user]);

  const rows: Row[] = useMemo(() => {
    const dqByDataset = new Map(dqList.map((dq) => [dq.dataset_id, dq]));
    const effectiveByDataset = new Map(effectiveList.map((eq) => [eq.dataset_id, eq]));

    return datasets.map((dataset) => {
      const dq = dqByDataset.get(dataset.id) ?? null;
      const effective = effectiveByDataset.get(dataset.id) ?? null;
      const score =
        effective?.effective_score ?? (dq?.overall_score != null ? dq.overall_score : null);
      return { dataset, dq, effective, score };
    });
  }, [datasets, dqList, effectiveList]);

  const availableDomains = useMemo(() => {
    return Array.from(
      new Set(datasets.map((d) => d.domain).filter((d): d is string => Boolean(d)))
    ).sort();
  }, [datasets]);

  const filteredRows = useMemo(() => {
    return rows
      .filter((row) => {
        if (search.trim()) {
          const needle = search.trim().toLowerCase();
          const haystack = `${row.dataset.schema_name}.${row.dataset.name}`.toLowerCase();
          if (!haystack.includes(needle)) return false;
        }
        if (domainFilter !== "ALL" && row.dataset.domain !== domainFilter) return false;
        if (thresholdFilter === "BELOW_80" && !(row.score !== null && row.score < 80)) return false;
        if (thresholdFilter === "BELOW_50" && !(row.score !== null && row.score < 50)) return false;
        if (thresholdFilter === "UNPROFILED" && row.score !== null) return false;
        return true;
      })
      .sort((a, b) => {
        // Worst-first: lowest score surfaces first, unprofiled datasets last.
        if (a.score === null && b.score === null) return 0;
        if (a.score === null) return 1;
        if (b.score === null) return -1;
        return a.score - b.score;
      });
  }, [rows, search, domainFilter, thresholdFilter]);

  const stats = useMemo(() => {
    const profiled = rows.filter((r) => r.score !== null);
    const average =
      profiled.length > 0
        ? Math.round(profiled.reduce((sum, r) => sum + (r.score ?? 0), 0) / profiled.length)
        : null;
    const belowFifty = rows.filter((r) => r.score !== null && r.score < 50).length;
    const unprofiled = rows.filter((r) => r.score === null).length;
    return { total: rows.length, average, belowFifty, unprofiled };
  }, [rows]);

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
        <h1 className="text-4xl font-bold">Data Quality</h1>
        <p className="mt-2 max-w-2xl text-gray-600">
          Profiled completeness, uniqueness, validity, consistency, and freshness across
          every dataset in the catalog, blended with what each one inherits from upstream
          lineage. Sorted worst-first so the datasets that need attention surface at the top.
        </p>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-xl bg-white p-4 shadow">
          <div className="text-2xl font-bold">{stats.total}</div>
          <div className="text-xs text-gray-500">Total datasets</div>
        </div>
        <div className="rounded-xl bg-white p-4 shadow">
          <div className="text-2xl font-bold">{stats.average ?? "-"}</div>
          <div className="text-xs text-gray-500">Average score</div>
        </div>
        <div className="rounded-xl bg-white p-4 shadow">
          <div className="text-2xl font-bold text-red-600">{stats.belowFifty}</div>
          <div className="text-xs text-gray-500">Below 50</div>
        </div>
        <div className="rounded-xl bg-white p-4 shadow">
          <div className="text-2xl font-bold text-gray-500">{stats.unprofiled}</div>
          <div className="text-xs text-gray-500">Unprofiled</div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search datasets..."
          className="rounded-lg border px-3 py-2 text-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="rounded-lg border px-3 py-2 text-sm"
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
        >
          <option value="ALL">All domains</option>
          {availableDomains.map((domain) => (
            <option key={domain} value={domain}>
              {domain}
            </option>
          ))}
        </select>
        <select
          className="rounded-lg border px-3 py-2 text-sm"
          value={thresholdFilter}
          onChange={(e) => setThresholdFilter(e.target.value as ThresholdFilter)}
        >
          <option value="ALL">All scores</option>
          <option value="BELOW_80">Below 80</option>
          <option value="BELOW_50">Below 50 (worst offenders)</option>
          <option value="UNPROFILED">Unprofiled only</option>
        </select>
      </div>

      {loading ? (
        <div className="rounded-xl bg-white p-8 text-center text-gray-500 shadow">Loading...</div>
      ) : filteredRows.length === 0 ? (
        <div className="rounded-xl border border-dashed bg-white p-8 text-center text-gray-500">
          No datasets match these filters.
        </div>
      ) : (
        <div className="space-y-3">
          {filteredRows.map((row) => (
            <div key={row.dataset.id} className="rounded-xl bg-white p-5 shadow">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <Link
                      href={`/datasets/${row.dataset.id}`}
                      className="font-semibold hover:underline"
                    >
                      {row.dataset.schema_name}.{row.dataset.name}
                    </Link>
                    {row.dataset.domain && (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700">
                        {row.dataset.domain}
                      </span>
                    )}
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-5">
                    {DIMENSIONS.map(({ key, label }) => {
                      const raw = row.dq?.[key];
                      const value = typeof raw === "number" ? Math.round(raw) : null;
                      return (
                        <div key={key}>
                          <div className="mb-1 flex items-center justify-between text-[10px]">
                            <span className="text-gray-500">{label}</span>
                            <span className="font-medium text-gray-700">
                              {value === null ? "-" : `${value}%`}
                            </span>
                          </div>
                          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                            {value !== null && (
                              <div
                                className={`h-full rounded-full ${barColor(value)}`}
                                style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
                              />
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <span
                    className={`rounded-full px-3 py-1 text-sm font-semibold ${scoreBadgeClasses(
                      row.score
                    )}`}
                    title={
                      row.effective?.effective_score != null
                        ? "Lineage-adjusted effective score"
                        : "Own profiled score"
                    }
                  >
                    {row.score !== null ? Math.round(row.score) : "No profile"}
                  </span>
                  {row.effective?.own_score != null &&
                    row.effective?.effective_score != null &&
                    Math.round(row.effective.effective_score) !== Math.round(row.effective.own_score) && (
                      <span className="text-[10px] text-gray-500">
                        own: {Math.round(row.effective.own_score)}
                      </span>
                    )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
