"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AddSourceCard from "../components/AddSourceCard";
import DemoDataPanel from "../components/DemoDataPanel";
import ScanButton from "../components/ScanButton";
import TopNav from "../components/TopNav";

import { useAuth } from "../contexts/AuthContext";

import api from "../services/api";

import type {
  Dataset,
  GovernanceThread,
  Source
} from "../types/metadata";
import { getOverallHealth, HEALTH_STYLES } from "../utils/datasetHealth";
import { stewardshipGaps } from "../utils/stewardshipGaps";

function isOperationalAlert(dataset: Dataset) {
  return (
    dataset.operational_status === "DEGRADED" ||
    dataset.operational_status === "AT_RISK" ||
    dataset.operational_status === "UNSTABLE"
  );
}

function StatChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-gray-50 px-2.5 py-1.5 text-center">
      <div className="text-sm font-semibold leading-none">{value}</div>
      <div className="text-[10px] text-gray-500 mt-0.5">{label}</div>
    </div>
  );
}

export default function Home() {

  const { user, loading: authLoading } = useAuth();

  const [sources, setSources] = useState<Source[]>([]);

  const [datasets, setDatasets] = useState<Dataset[]>([]);

  const [openThreadCounts, setOpenThreadCounts] = useState<Record<string, number>>({});

  // Deep-linkable from the guided tour (?q=payments) - read once,
  // lazily, via window.location.search rather than useSearchParams()
  // (which requires a Suspense boundary in the app router) - same
  // pattern DiscussionsPage uses for its filters.
  const [search, setSearch] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("q") ?? "";
  });
  const [domainFilter, setDomainFilter] = useState("ALL");
  const [sensitivityFilter, setSensitivityFilter] = useState("ALL");
  const [certificationFilter, setCertificationFilter] = useState("ALL");
  const [governanceFilter, setGovernanceFilter] = useState("ALL");
  const [dataCategoryFilter, setDataCategoryFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState("trust_score");

  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canManageSources = user?.role !== "viewer";

  // Role-differentiated landing content: the backend has enforced
  // these roles for a while (RBAC on every mutating endpoint), but
  // until now everyone landed on the exact same generic catalog page
  // regardless of role. Admin sees every panel below (admin can act
  // in every capacity, same convention as require_role() throughout
  // the backend) - Data Owner and Steward each get the queue that
  // matches what they're actually here to do, Viewer gets a lighter
  // page since they can't act on any of it anyway.
  const isDataOwner = user?.role === "admin" || user?.role === "data_owner";
  const isSteward = user?.role === "admin" || user?.role === "steward";
  const isViewerOnly = user?.role === "viewer";

  // Not logged in: send the visitor to the full marketing site
  // (frontend/public/site.html) instead of forcing straight to /login -
  // it lives as a static asset on this same origin, so one tunnel/host
  // covers pitch + product without a separate app. subdomain.
  useEffect(() => {
    if (!authLoading && !user) {
      window.location.replace("/site.html");
    }
  }, [authLoading, user]);

  useEffect(() => {

    if (!user) return;

    async function fetchMetadata() {

      try {

        setErrorMessage(null);

        const sourceResponse = await api.get<Source[]>(
          "/api/sources"
        );

        const datasetResponse = await api.get<Dataset[]>(
          "/api/datasets"
        );

        setSources(sourceResponse.data);

        setDatasets(datasetResponse.data);

      } catch (error) {

        console.error(error);

        setErrorMessage(
          "Unable to load metadata. Please make sure the backend is running on http://127.0.0.1:8000."
        );
      }
    }

    async function fetchOpenThreadCounts() {
      try {
        const response = await api.get<GovernanceThread[]>("/api/discussions?status=OPEN");
        const counts: Record<string, number> = {};
        for (const thread of response.data) {
          if (!thread.dataset_id) continue;
          counts[thread.dataset_id] = (counts[thread.dataset_id] || 0) + 1;
        }
        setOpenThreadCounts(counts);
      } catch (error) {
        console.error(error);
      }
    }

    fetchMetadata();
    fetchOpenThreadCounts();

  }, [user]);

  const normalizedSearch = (
    search
      .trim()
      .toLowerCase()
  );

  const availableDomains = Array.from(
    new Set(
      datasets
        .map((dataset) => dataset.domain)
        .filter((domain): domain is string => Boolean(domain))
    )
  ).sort();

  const availableCertifications = Array.from(
    new Set(
      datasets
        .map((dataset) => dataset.certification)
        .filter((certification): certification is string => Boolean(certification))
    )
  ).sort();

  const filtersActive =
    normalizedSearch !== "" ||
    domainFilter !== "ALL" ||
    sensitivityFilter !== "ALL" ||
    certificationFilter !== "ALL" ||
    governanceFilter !== "ALL" ||
    dataCategoryFilter !== "ALL";

  function clearFilters() {
    setSearch("");
    setDomainFilter("ALL");
    setSensitivityFilter("ALL");
    setCertificationFilter("ALL");
    setGovernanceFilter("ALL");
    setDataCategoryFilter("ALL");
  }

  const filteredDatasets = datasets
  .filter((dataset) => {

    const searchableText = [

      dataset.schema_name,

      dataset.name,

      dataset.owner,

      dataset.governance_status,

      dataset.sensitivity_score,

      dataset.tags,

    ]
      .join(" ")
      .toLowerCase();

    if (!searchableText.includes(normalizedSearch)) {
      return false;
    }

    if (domainFilter !== "ALL" && dataset.domain !== domainFilter) {
      return false;
    }

    if (sensitivityFilter !== "ALL" && dataset.sensitivity_score !== sensitivityFilter) {
      return false;
    }

    if (certificationFilter !== "ALL" && dataset.certification !== certificationFilter) {
      return false;
    }

    if (governanceFilter !== "ALL" && dataset.governance_status !== governanceFilter) {
      return false;
    }

    if (dataCategoryFilter !== "ALL" && dataset.data_category !== dataCategoryFilter) {
      return false;
    }

    return true;
  })
  .sort((a, b) => {

    if (sortBy === "name") {
      return `${a.schema_name}.${a.name}`.localeCompare(`${b.schema_name}.${b.name}`);
    }

    if (sortBy === "governance_score") {
      return (b.governance_score || 0) - (a.governance_score || 0);
    }

    if (sortBy === "quality_score") {
      return (b.quality_score || 0) - (a.quality_score || 0);
    }

    if (sortBy === "most_viewed") {
      return (b.view_count || 0) - (a.view_count || 0);
    }

    // trust_score: lowest first, so the riskiest datasets surface at
    // the top - this matches the original default ordering.
    return (a.trust_score || 0) - (b.trust_score || 0);
  });
  const totalDatasets = datasets.length;

    const highRiskDatasets = datasets.filter(
    (dataset) =>
        dataset.sensitivity_score === "HIGH"
).length;

    const totalPIIColumns = datasets.reduce(
    (total, dataset) =>
      total + (dataset.pii_columns || 0),
    0
  );

  const unhealthyDatasets = datasets.filter(
    (dataset) =>
      dataset.governance_status !== "HEALTHY"
  ).length;

  const unstableDatasets = datasets.filter(
    isOperationalAlert
  ).length;

  const dataCategoryBreakdown = (
    ["MASTER", "REFERENCE", "TRANSACTIONAL", "ANALYTICAL"] as const
  ).map((category) => ({
    category,
    label:
      category === "MASTER"
        ? "Master Data"
        : category === "REFERENCE"
        ? "Reference Data"
        : category === "TRANSACTIONAL"
        ? "Transactional Data"
        : "Analytical Data",
    count: datasets.filter((dataset) => dataset.data_category === category).length,
  }));

  // Data Owner queue: datasets with a certification request awaiting
  // action. pending_certification_request_id already comes back on
  // the /api/datasets payload, so this needs no extra fetch.
  const pendingApprovalDatasets = datasets.filter(
    (dataset) => dataset.pending_certification_request_id
  );

  // Steward queue: anything a steward should actually go fix -
  // missing ownership/stewardship/domain/description, or a
  // governance score low enough to flag. Computed client-side since
  // there's no "missing X" filter on the backend yet, from data
  // already on hand. Gap-detection logic lives in
  // utils/stewardshipGaps.ts so it's unit-testable on its own.
  const stewardshipGapDatasets = datasets
    .map((dataset) => ({ dataset, gaps: stewardshipGaps(dataset) }))
    .filter(({ gaps }) => gaps.length > 0);

  if (authLoading) {
    return (
      <main className="min-h-screen p-10 bg-gray-100">
        <div className="rounded-lg bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  // Not logged in: the useEffect above is already navigating to
  // /site.html - render the same loading state in the brief window
  // before that completes, rather than flashing dashboard chrome.
  if (!user) {
    return (
      <main className="min-h-screen p-10 bg-gray-100">
        <div className="rounded-lg bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  return (

    <main className="min-h-screen p-10 bg-gray-100">

      <TopNav />

      <div className="mb-8">
        <h1 className="text-4xl font-bold">DataFe</h1>
        <p className="mt-1 text-gray-500">Metadata intelligence and governance platform</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-5 gap-6 mb-8">

        <div className="bg-white rounded-xl p-6 shadow">
            <div className="text-sm text-gray-500">
            Total Datasets
            </div>

            <div className="text-4xl font-bold mt-2">
            {totalDatasets}
            </div>
        </div>

        <div className="bg-white rounded-xl p-6 shadow">
            <div className="text-sm text-gray-500">
            High Risk
            </div>

            <div className="text-4xl font-bold mt-2 text-red-600">
            {highRiskDatasets}
            </div>
        </div>

        <div className="bg-white rounded-xl p-6 shadow">
            <div className="text-sm text-gray-500">
            PII Columns
            </div>

            <div className="text-4xl font-bold mt-2 text-orange-600">
            {totalPIIColumns}
            </div>
        </div>

        <div className="bg-white rounded-xl p-6 shadow">
            <div className="text-sm text-gray-500">
            Governance Alerts
            </div>

            <div className="text-4xl font-bold mt-2 text-yellow-600">
            {unhealthyDatasets}
            </div>
        </div>

        <div className="bg-white rounded-xl p-6 shadow">
            <div className="text-sm text-gray-500">
            Operational Alerts
            </div>

            <div className="text-4xl font-bold mt-2 text-red-600">
            {unstableDatasets}
            </div>
        </div>

</div>

      {totalDatasets > 0 && (
        <div className="mb-8 flex flex-wrap items-center gap-3 rounded-xl bg-white p-4 shadow">
          <span className="text-sm text-gray-500">Data by category:</span>
          {dataCategoryBreakdown.map(({ category, label, count }) => (
            <button
              key={category}
              onClick={() =>
                setDataCategoryFilter((prev) => (prev === category ? "ALL" : category))
              }
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                dataCategoryFilter === category
                  ? "bg-black text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              {label} · {count}
            </button>
          ))}
        </div>
      )}

      {isDataOwner && pendingApprovalDatasets.length > 0 && (
        <div className="mb-8 rounded-xl border border-blue-200 bg-blue-50 p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-blue-900">
              Pending your approval ({pendingApprovalDatasets.length})
            </h2>
            <span className="text-xs text-blue-700">Certification requests awaiting a Data Owner</span>
          </div>
          <div className="space-y-2">
            {pendingApprovalDatasets.map((dataset) => (
              <Link
                key={dataset.id}
                href={`/datasets/${dataset.id}`}
                className="flex items-center justify-between rounded-lg bg-white px-4 py-2.5 text-sm shadow-sm hover:shadow"
              >
                <span className="font-medium">
                  {dataset.schema_name}.{dataset.name}
                </span>
                <span className="text-xs text-blue-700">Review certification &rarr;</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {isSteward && stewardshipGapDatasets.length > 0 && (
        <div className="mb-8 rounded-xl border border-amber-200 bg-amber-50 p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-amber-900">
              Stewardship gaps ({stewardshipGapDatasets.length})
            </h2>
            <span className="text-xs text-amber-700">
              Missing ownership, stewardship, domain, description, or a low governance score
            </span>
          </div>
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {stewardshipGapDatasets.map(({ dataset, gaps }) => (
              <Link
                key={dataset.id}
                href={`/datasets/${dataset.id}`}
                className="flex items-center justify-between rounded-lg bg-white px-4 py-2.5 text-sm shadow-sm hover:shadow"
              >
                <span className="font-medium">
                  {dataset.schema_name}.{dataset.name}
                </span>
                <span className="text-xs text-gray-500">{gaps.join(" · ")}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {isViewerOnly && (
        <div className="mb-8 rounded-xl bg-white p-4 text-sm text-gray-600 shadow">
          Browse the catalog below to find and understand data. Need a new source connected
          or governance details changed? Ask an editor on your team.
        </div>
      )}

      {canManageSources && (
        <DemoDataPanel />
      )}

      {canManageSources && (
        <AddSourceCard />
      )}

      {errorMessage && (

        <div
          className="
            mb-6
            rounded
            border
            border-red-200
            bg-red-50
            p-4
            text-red-700
          "
        >
          {errorMessage}
        </div>

      )}

      <div className="mb-6 rounded-xl bg-white p-4 shadow">

        <input
          type="text"
          placeholder="Search datasets by name, owner, tag..."
          value={search}
          onChange={(e) =>
            setSearch(e.target.value)
          }
          className="
            w-full
            p-3
            rounded-xl
            border
            mb-3
          "
        />

        <div className="flex flex-wrap items-center gap-3">
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
            value={sensitivityFilter}
            onChange={(e) => setSensitivityFilter(e.target.value)}
          >
            <option value="ALL">All sensitivity levels</option>
            <option value="LOW">Low sensitivity</option>
            <option value="MEDIUM">Medium sensitivity</option>
            <option value="HIGH">High sensitivity</option>
          </select>

          <select
            className="rounded-lg border px-3 py-2 text-sm"
            value={certificationFilter}
            onChange={(e) => setCertificationFilter(e.target.value)}
          >
            <option value="ALL">All certifications</option>
            {availableCertifications.map((certification) => (
              <option key={certification} value={certification}>
                {certification}
              </option>
            ))}
          </select>

          <select
            className="rounded-lg border px-3 py-2 text-sm"
            value={governanceFilter}
            onChange={(e) => setGovernanceFilter(e.target.value)}
          >
            <option value="ALL">All governance statuses</option>
            <option value="HEALTHY">Healthy</option>
            <option value="REVIEW_REQUIRED">Review required</option>
            <option value="CRITICAL">Critical</option>
          </select>

          <select
            className="rounded-lg border px-3 py-2 text-sm"
            value={dataCategoryFilter}
            onChange={(e) => setDataCategoryFilter(e.target.value)}
          >
            <option value="ALL">All data categories</option>
            <option value="MASTER">Master data</option>
            <option value="REFERENCE">Reference data</option>
            <option value="TRANSACTIONAL">Transactional data</option>
            <option value="ANALYTICAL">Analytical data</option>
          </select>

          <select
            className="rounded-lg border px-3 py-2 text-sm"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="trust_score">Sort: Riskiest first</option>
            <option value="governance_score">Sort: Governance score</option>
            <option value="quality_score">Sort: Quality score</option>
            <option value="most_viewed">Sort: Most viewed</option>
            <option value="name">Sort: Name (A-Z)</option>
          </select>

          {filtersActive && (
            <button
              onClick={clearFilters}
              className="rounded-lg border px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Clear filters
            </button>
          )}

          <span className="ml-auto text-sm text-gray-500">
            {filteredDatasets.length} of {totalDatasets} datasets
          </span>
        </div>

      </div>

      <div
        className={
          canManageSources
            ? "grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-7"
            : ""
        }
      >

        {canManageSources && (
          <div className="bg-white rounded-xl p-6 shadow">

            <h2 className="text-2xl font-semibold mb-4">
              Sources
            </h2>

            <div className="space-y-3">

              {sources.map((source) => (

                <div
                  key={source.id}
                  className="
                    border
                    rounded-lg
                    p-4
                    bg-gray-50
                  "
                >

                  <div className="font-semibold flex items-center gap-2">
                    {source.name}
                    {source.is_seed_data && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700">
                        Demo
                      </span>
                    )}
                  </div>

                  <div className="text-sm text-gray-500 mt-1">
                    Type: {source.type}
                  </div>

                  {source.type !== "file_upload" && (
                    <ScanButton sourceId={source.id} />
                  )}

                </div>

              ))}

              {sources.length === 0 && (

                <div className="text-gray-500">
                  No sources registered yet.
                </div>

              )}

            </div>

          </div>
        )}

        <div className="bg-white rounded-xl p-6 shadow">

          <h2 className="text-2xl font-semibold mb-4">
            Datasets
          </h2>

          <div
            className={
              canManageSources
                ? "space-y-4"
                : "grid grid-cols-1 xl:grid-cols-2 gap-4"
            }
          >

            {filteredDatasets.map((dataset) => {
              const health = getOverallHealth(dataset);
              const healthStyle = HEALTH_STYLES[health.level];
              const openThreads = openThreadCounts[dataset.id] || 0;

              return (
                <Link
                  href={`/datasets/${dataset.id}`}
                  key={dataset.id}
                  className="block border rounded-xl p-4 hover:bg-gray-50 hover:shadow-sm transition"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-semibold text-lg truncate">
                        {dataset.schema_name}.{dataset.name}
                      </div>
                      <div className="text-sm text-gray-500 mt-0.5 line-clamp-2">
                        {dataset.ai_summary || dataset.description || "No description available"}
                      </div>
                    </div>

                    <span
                      className={`shrink-0 text-xs px-2.5 py-1 rounded-full font-medium ${healthStyle.bg} ${healthStyle.text}`}
                    >
                      {healthStyle.label}
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-2 mt-3">
                    <StatChip label="Trust" value={dataset.trust_score || 0} />
                    <StatChip label="Quality" value={dataset.quality_score || 0} />
                    <StatChip label="Governance" value={dataset.governance_score || 0} />
                    <StatChip label="Columns" value={dataset.total_columns || 0} />
                  </div>

                  <div className="flex flex-wrap items-center gap-2 mt-3">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        dataset.sensitivity_score === "HIGH"
                          ? "bg-red-100 text-red-700"
                          : dataset.sensitivity_score === "MEDIUM"
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-green-100 text-green-700"
                      }`}
                    >
                      {dataset.sensitivity_score || "LOW"} sensitivity
                    </span>

                    {dataset.data_category && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 capitalize">
                        {dataset.data_category.toLowerCase()}
                      </span>
                    )}

                    {dataset.system_role && (
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          dataset.system_role === "SYSTEM_OF_RECORD"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-purple-100 text-purple-700"
                        }`}
                      >
                        {dataset.system_role === "SYSTEM_OF_RECORD" ? "SoR" : "SoRef"}
                      </span>
                    )}

                    {dataset.certification === "VERIFIED" && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                        ✓ Verified
                      </span>
                    )}

                    {dataset.contract_status === "BREACHED" && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">
                        Contract breached
                      </span>
                    )}

                    {openThreads > 0 && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">
                        {openThreads} open {openThreads === 1 ? "thread" : "threads"}
                      </span>
                    )}
                  </div>

                  <div className="text-xs text-gray-400 mt-3">
                    Owner: {dataset.owner || "Unassigned"}
                    {dataset.domain ? ` · ${dataset.domain}` : ""}
                    {(dataset.view_count || 0) > 0 ? ` · viewed ${dataset.view_count}×` : ""}
                  </div>
                </Link>
              );
            })}

            {filteredDatasets.length === 0 && (

              <div className="text-gray-500 py-3">
                No datasets found.
              </div>

            )}

          </div>

        </div>

      </div>

    </main>
  );
}
