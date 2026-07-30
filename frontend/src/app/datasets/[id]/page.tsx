"use client";

import { Fragment, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import BusinessViewPanel from "../../../components/BusinessViewPanel";
import CertificationWorkflowPanel from "../../../components/CertificationWorkflowPanel";
import CreateLineageForm from "../../../components/CreateLineageForm";
import DataContractPanel from "../../../components/DataContractPanel";
import DatasetDiscussionPanel from "../../../components/DatasetDiscussionPanel";
import LineageEdgeCard from "../../../components/LineageEdgeCard";
import TopNav from "../../../components/TopNav";
import { useRequireAuth } from "../../../hooks/useRequireAuth";
import api from "../../../services/api";
import type {
  Classification,
  ColumnLineage,
  ConsentStatus,
  DataQuality,
  Dataset,
  DatasetColumn,
  DatasetGovernanceUpdate,
  EffectiveQuality,
  GovernanceScorecard,
  Lineage,
} from "../../../types/metadata";
import { getOverallHealth, HEALTH_STYLES } from "../../../utils/datasetHealth";

const CONSENT_STATUS_OPTIONS: ConsentStatus[] = [
  "NOT_ASSESSED",
  "CONSENT_OBTAINED",
  "CONSENT_NOT_REQUIRED",
];

type TabKey = "overview" | "business" | "columns" | "lineage" | "governance" | "discussion";

export default function DatasetPage() {
  const { id } = useParams() as { id?: string };
  const { user, loading: authLoading } = useRequireAuth();

  // Deep-linkable from the guided tour (?tab=governance) - same
  // window.location.search read pattern used elsewhere (DiscussionsPage,
  // the catalog page, the lineage page) rather than useSearchParams(),
  // so this page doesn't need a Suspense boundary.
  const [activeTab, setActiveTab] = useState<TabKey>(() => {
    if (typeof window === "undefined") return "overview";
    const raw = new URLSearchParams(window.location.search).get("tab");
    const valid: TabKey[] = ["overview", "business", "columns", "lineage", "governance", "discussion"];
    return (valid as string[]).includes(raw ?? "") ? (raw as TabKey) : "overview";
  });

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [columns, setColumns] = useState<DatasetColumn[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [columnErrorMessage, setColumnErrorMessage] = useState<string | null>(null);
  const [summary, setSummary] = useState("");

  const [scorecard, setScorecard] = useState<GovernanceScorecard | null>(null);
  const [dataQuality, setDataQuality] = useState<DataQuality | null>(null);
  const [dataQualityMessage, setDataQualityMessage] = useState<string | null>(null);
  const [effectiveQuality, setEffectiveQuality] = useState<EffectiveQuality | null>(null);

  const [dependencies, setDependencies] = useState<Lineage[]>([]);
  const [impact, setImpact] = useState<Lineage[]>([]);
  const [allDatasets, setAllDatasets] = useState<Dataset[]>([]);

  const [columnLineageUpstream, setColumnLineageUpstream] = useState<ColumnLineage[]>([]);
  const [columnLineageDownstream, setColumnLineageDownstream] = useState<ColumnLineage[]>([]);

  const [form, setForm] = useState<DatasetGovernanceUpdate>({});
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [governanceEditMode, setGovernanceEditMode] = useState(false);

  const [expandedColumnId, setExpandedColumnId] = useState<string | null>(null);
  const [columnDescriptionDrafts, setColumnDescriptionDrafts] = useState<Record<string, string>>({});
  const [savingColumnId, setSavingColumnId] = useState<string | null>(null);
  const [savingMaskColumnId, setSavingMaskColumnId] = useState<string | null>(null);

  const canEditGovernance = user?.role === "admin" || user?.role === "steward";
  // Masking is deliberately narrower than description-editing: it's a
  // Data Owner/admin control, not a steward one - stewards document
  // data, Data Owners control who's allowed to see it.
  const canMaskColumns = user?.role === "admin" || user?.role === "data_owner";

  function toggleColumnExpanded(column: DatasetColumn) {
    if (expandedColumnId === column.id) {
      setExpandedColumnId(null);
      return;
    }
    setExpandedColumnId(column.id);
    setColumnDescriptionDrafts((prev) => ({
      ...prev,
      [column.id]: prev[column.id] ?? column.description ?? "",
    }));
  }

  async function handleSaveColumnDescription(columnId: string) {
    setSavingColumnId(columnId);
    try {
      const response = await api.patch<DatasetColumn>(`/api/columns/${columnId}`, {
        description: columnDescriptionDrafts[columnId] || null,
      });
      setColumns((prev) =>
        prev.map((column) => (column.id === columnId ? response.data : column))
      );
    } catch (error) {
      console.error(error);
    } finally {
      setSavingColumnId(null);
    }
  }

  async function handleToggleColumnMasking(column: DatasetColumn) {
    setSavingMaskColumnId(column.id);
    try {
      const response = await api.patch<DatasetColumn>(`/api/columns/${column.id}/masking`, {
        masked: !column.masked,
      });
      setColumns((prev) =>
        prev.map((c) => (c.id === column.id ? response.data : c))
      );
    } catch (error) {
      console.error(error);
    } finally {
      setSavingMaskColumnId(null);
    }
  }

  function parseSampleValues(raw?: string | null): string[] {
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.map((v) => (v === null ? "null" : String(v))) : [];
    } catch {
      return [];
    }
  }

  function resetFormFromScorecard(sc: GovernanceScorecard) {
    setForm({
      owner: sc.owner || "",
      steward: sc.steward || "",
      domain: sc.domain || "",
      tags: sc.tags || "",
      certification: sc.certification || "DRAFT",
      purpose: sc.purpose || "",
      consent_status: sc.consent_status || "NOT_ASSESSED",
      retention_period_days: sc.retention_period_days ?? undefined,
      retention_notes: sc.retention_notes || "",
      system_role: sc.system_role ?? null,
      data_category: sc.data_category ?? null,
    });
  }

  async function fetchLineageForDataset() {
    if (!id) return;
    try {
      const [dependenciesResponse, impactResponse] = await Promise.all([
        api.get<Lineage[]>(`/api/lineage/${id}/dependencies`),
        api.get<Lineage[]>(`/api/lineage/${id}/impact`),
      ]);
      setDependencies(dependenciesResponse.data);
      setImpact(impactResponse.data);
    } catch (error) {
      console.error(error);
    }
  }

  async function fetchColumnLineageForDataset() {
    if (!id) return;
    try {
      const response = await api.get<{ upstream: ColumnLineage[]; downstream: ColumnLineage[] }>(
        `/api/column-lineage/dataset/${id}`
      );
      setColumnLineageUpstream(response.data.upstream);
      setColumnLineageDownstream(response.data.downstream);
    } catch (error) {
      console.error(error);
    }
  }

  useEffect(() => {
    async function fetchDataset() {
      try {
        setErrorMessage(null);
        if (!id) return;
        const datasetResponse = await api.get<Dataset>(`/api/datasets/${id}`);
        setDataset(datasetResponse.data);
      } catch (error) {
        console.error(error);
        setErrorMessage(
          "Unable to load this dataset. Please check that the backend is running and the dataset still exists."
        );
      }
    }

    async function fetchColumns() {
      try {
        if (!id) return;
        setColumnErrorMessage(null);
        const columnResponse = await api.get<DatasetColumn[]>(`/api/columns/dataset/${id}`);
        setColumns(columnResponse.data);
      } catch (error) {
        console.error(error);
        setColumns([]);
        setColumnErrorMessage("Unable to load columns right now.");
      }
    }

    async function fetchSummary() {
      try {
        if (!id) return;
        const response = await api.get(`/api/datasets/${id}/summary`);
        setSummary(response.data.summary);
      } catch (error) {
        console.error(error);
      }
    }

    async function fetchScorecard() {
      try {
        if (!id) return;
        const response = await api.get<GovernanceScorecard>(
          `/api/governance/datasets/${id}/scorecard`
        );
        setScorecard(response.data);
        resetFormFromScorecard(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    async function fetchDataQuality() {
      try {
        if (!id) return;
        setDataQualityMessage(null);
        const response = await api.get<DataQuality>(`/api/data-quality/dataset/${id}`);
        setDataQuality(response.data);
      } catch (error) {
        console.error(error);
        setDataQuality(null);
        setDataQualityMessage("No data quality profile yet - run a scan to generate one.");
      }
    }

    async function fetchEffectiveQuality() {
      try {
        if (!id) return;
        const response = await api.get<EffectiveQuality>(
          `/api/data-quality/dataset/${id}/effective`
        );
        setEffectiveQuality(response.data);
      } catch (error) {
        console.error(error);
        setEffectiveQuality(null);
      }
    }

    async function fetchAllDatasets() {
      try {
        const response = await api.get<Dataset[]>("/api/datasets");
        setAllDatasets(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    if (!user) return;

    async function loadLineage() {
      await fetchLineageForDataset();
    }

    async function loadColumnLineage() {
      await fetchColumnLineageForDataset();
    }

    fetchDataset();
    fetchColumns();
    fetchSummary();
    fetchScorecard();
    fetchDataQuality();
    fetchEffectiveQuality();
    loadLineage();
    loadColumnLineage();
    fetchAllDatasets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, user]);

  async function handleSaveGovernance() {
    if (!id) return;

    setSaving(true);
    setSaveMessage(null);

    try {
      const response = await api.patch<GovernanceScorecard>(
        `/api/governance/datasets/${id}`,
        {
          owner: form.owner || null,
          steward: form.steward || null,
          domain: form.domain || null,
          tags: form.tags || null,
          certification: form.certification || null,
          purpose: form.purpose || null,
          consent_status: form.consent_status,
          retention_period_days:
            form.retention_period_days === undefined || form.retention_period_days === null
              ? null
              : Number(form.retention_period_days),
          retention_notes: form.retention_notes || null,
          system_role: form.system_role || null,
          data_category: form.data_category || null,
        }
      );
      setScorecard(response.data);
      setDataset((prev) =>
        prev
          ? {
              ...prev,
              owner: response.data.owner ?? prev.owner,
              steward: response.data.steward ?? prev.steward,
              domain: response.data.domain ?? prev.domain,
              tags: response.data.tags ?? prev.tags,
              certification: response.data.certification ?? prev.certification,
              system_role: response.data.system_role ?? prev.system_role,
              data_category: response.data.data_category ?? prev.data_category,
            }
          : prev
      );
      setSaveMessage("Saved.");
      setGovernanceEditMode(false);
    } catch (error) {
      console.error(error);
      setSaveMessage("Unable to save changes.");
    } finally {
      setSaving(false);
    }
  }

  function cancelGovernanceEdit() {
    if (scorecard) resetFormFromScorecard(scorecard);
    setSaveMessage(null);
    setGovernanceEditMode(false);
  }

  function getBadgeColor(classification: Classification) {
    if (classification === "PII") return "bg-red-500";
    if (classification === "SENSITIVE") return "bg-yellow-500";
    return "bg-green-500";
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen p-10 bg-gray-100">
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  if (errorMessage) {
    return (
      <main className="min-h-screen p-10 bg-gray-100">
        <TopNav />
        <div className="bg-white rounded p-6 shadow">
          <h1 className="text-2xl font-semibold mb-2">Dataset unavailable</h1>
          <p className="text-gray-600">{errorMessage}</p>
        </div>
      </main>
    );
  }

  if (!dataset) {
    return (
      <main className="min-h-screen p-10 bg-gray-100">
        <TopNav />
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  const health = getOverallHealth(dataset);
  const healthStyle = HEALTH_STYLES[health.level];

  const tabs: { key: TabKey; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "business", label: "Business View" },
    { key: "columns", label: `Columns (${columns.length})` },
    {
      key: "lineage",
      label: `Lineage (${dependencies.length + impact.length + columnLineageUpstream.length + columnLineageDownstream.length})`,
    },
    { key: "governance", label: "Governance" },
    { key: "discussion", label: "Discussion" },
  ];

  return (
    <main className="min-h-screen p-10 bg-gray-100">
      <TopNav />

      <div className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-4xl font-bold">
              {dataset.schema_name}.{dataset.name}
            </h1>
            <div className="text-gray-600 mt-1">Owner: {dataset.owner}</div>
          </div>

          <div className={`shrink-0 rounded-xl px-4 py-3 ${healthStyle.bg}`}>
            <div className={`text-sm font-semibold ${healthStyle.text}`}>
              {healthStyle.label}
            </div>
            {health.reasons.length > 0 && (
              <div className={`text-xs mt-1 max-w-xs ${healthStyle.text}`}>
                {health.reasons.join(", ")}
              </div>
            )}
          </div>
        </div>

        <div className="text-gray-600 mt-3 max-w-3xl">
          {dataset.description || "No dataset description available."}
        </div>

        {(dataset.ai_summary || summary) && (
          <div className="text-sm text-blue-700 mt-2 max-w-3xl">
            {dataset.ai_summary}
            {summary && <div className="mt-1">{summary}</div>}
          </div>
        )}

        <div className="flex flex-wrap gap-2 mt-4">
          <span
            className={`text-xs px-3 py-1 rounded-full ${
              dataset.sensitivity_score === "HIGH"
                ? "bg-red-100 text-red-700"
                : dataset.sensitivity_score === "MEDIUM"
                ? "bg-yellow-100 text-yellow-700"
                : "bg-green-100 text-green-700"
            }`}
          >
            Sensitivity: {dataset.sensitivity_score || "LOW"}
          </span>
          <span className="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-700">
            {dataset.pii_columns || 0} PII column{dataset.pii_columns === 1 ? "" : "s"}
          </span>
          <span className="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-700">
            Certification: {dataset.certification || "DRAFT"}
          </span>
          <span className="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-700">
            Quality: {dataset.quality_score || 0}/100
          </span>
          <span className="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-700">
            Trust: {dataset.trust_score || 0}/100
          </span>
          {(dataset.view_count || 0) > 0 && (
            <span className="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-700">
              Viewed {dataset.view_count}×
              {(dataset.distinct_viewer_count || 0) > 1
                ? ` by ${dataset.distinct_viewer_count} people`
                : ""}
            </span>
          )}
        </div>
      </div>

      <div className="mb-6 flex flex-wrap rounded-lg border bg-white text-sm overflow-hidden w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 ${
              activeTab === tab.key ? "bg-black text-white" : "hover:bg-gray-50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="bg-white rounded-xl p-6 shadow lg:col-span-2">
            <h2 className="text-xl font-semibold mb-4">Status Detail</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <div>
                <div className="text-sm text-gray-500">Governance</div>
                <div className="text-lg font-semibold mt-1">
                  {dataset.governance_status || "UNKNOWN"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Operational</div>
                <div className="text-lg font-semibold mt-1">
                  {dataset.operational_status || "UNKNOWN"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Freshness</div>
                <div className="text-lg font-semibold mt-1">
                  {dataset.freshness_status || "UNKNOWN"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Contract</div>
                <div className="text-lg font-semibold mt-1">
                  {dataset.contract_status || "NO_CONTRACT"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Privacy Score</div>
                <div className="text-lg font-semibold mt-1">
                  {scorecard ? `${scorecard.privacy_score}/100` : "…"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Total Columns</div>
                <div className="text-lg font-semibold mt-1">{dataset.total_columns || 0}</div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl p-6 shadow">
            <h2 className="text-xl font-semibold mb-4">Popularity</h2>
            <div className="text-3xl font-bold">{dataset.view_count || 0}</div>
            <div className="text-sm text-gray-500 mt-1">
              {dataset.view_count
                ? `viewed by ${dataset.distinct_viewer_count || 0} ${
                    dataset.distinct_viewer_count === 1 ? "person" : "people"
                  }`
                : "no views yet"}
            </div>
          </div>
        </div>
      )}

      {activeTab === "business" && (
        <BusinessViewPanel
          dataset={dataset}
          columns={columns}
          dataQuality={dataQuality}
          effectiveQuality={effectiveQuality}
          dependencies={dependencies}
          impact={impact}
          allDatasets={allDatasets}
          canEdit={canEditGovernance}
        />
      )}

      {activeTab === "columns" && (
        <div className="bg-white rounded-xl shadow p-6">
          <div
            className={`
              mb-6
              rounded-xl
              p-4
              text-sm
              ${
                dataset.sensitivity_score === "HIGH"
                  ? "bg-red-50 text-red-700 border border-red-200"
                  : dataset.sensitivity_score === "MEDIUM"
                  ? "bg-yellow-50 text-yellow-700 border border-yellow-200"
                  : "bg-green-50 text-green-700 border border-green-200"
              }
            `}
          >
            {dataset.sensitivity_score === "HIGH" &&
              "High privacy risk dataset. Contains multiple PII attributes."}
            {dataset.sensitivity_score === "MEDIUM" && "Moderate privacy exposure detected."}
            {(!dataset.sensitivity_score || dataset.sensitivity_score === "LOW") &&
              "Low privacy exposure."}
          </div>

          {columnErrorMessage && (
            <div className="text-red-600 mb-4">{columnErrorMessage}</div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3">Column</th>
                  <th className="text-left py-3">Type</th>
                  <th className="text-left py-3">Nullable</th>
                  <th className="text-left py-3">Classification</th>
                  <th className="text-left py-3">Sensitivity</th>
                  <th className="text-left py-3"></th>
                </tr>
              </thead>
              <tbody>
                {columns.map((column) => {
                  const isExpanded = expandedColumnId === column.id;
                  const sampleValues = parseSampleValues(column.sample_values);
                  const upstreamMappings = columnLineageUpstream.filter(
                    (edge) => edge.downstream_column_name === column.name
                  );
                  const downstreamMappings = columnLineageDownstream.filter(
                    (edge) => edge.upstream_column_name === column.name
                  );

                  return (
                    <Fragment key={column.id}>
                      <tr className="border-b hover:bg-gray-50">
                        <td className="py-3 font-medium">{column.name}</td>
                        <td className="py-3">{column.data_type}</td>
                        <td className="py-3">{column.nullable ? "YES" : "NO"}</td>
                        <td className="py-3">
                          <span
                            className={`
                              px-2
                              py-1
                              rounded-full
                              text-xs
                              text-white
                              ${getBadgeColor(column.classification)}
                            `}
                          >
                            {column.classification}
                          </span>
                          {column.masked && (
                            <span
                              title="Sample values are hidden from Viewers"
                              className="ml-1.5 rounded-full bg-amber-100 px-2 py-1 text-xs text-amber-800"
                            >
                              🔒 Masked
                            </span>
                          )}
                        </td>
                        <td className="py-3">{column.sensitivity_score || 0}</td>
                        <td className="py-3 text-right">
                          <button
                            onClick={() => toggleColumnExpanded(column)}
                            className="text-xs text-gray-500 hover:text-black"
                          >
                            {isExpanded ? "Hide details" : "Show details"}
                          </button>
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr className="border-b bg-gray-50">
                          <td colSpan={6} className="px-3 py-4">
                            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                              <div>
                                <div className="mb-1 text-xs font-semibold text-gray-500">
                                  Description
                                </div>
                                {canEditGovernance ? (
                                  <div>
                                    <textarea
                                      rows={3}
                                      className="w-full rounded-lg border px-3 py-2 text-sm"
                                      placeholder="What does this column represent?"
                                      value={columnDescriptionDrafts[column.id] ?? ""}
                                      onChange={(event) =>
                                        setColumnDescriptionDrafts((prev) => ({
                                          ...prev,
                                          [column.id]: event.target.value,
                                        }))
                                      }
                                    />
                                    <button
                                      onClick={() => handleSaveColumnDescription(column.id)}
                                      disabled={savingColumnId === column.id}
                                      className="mt-2 rounded-lg bg-black px-3 py-1.5 text-xs text-white hover:bg-gray-800 disabled:opacity-50"
                                    >
                                      {savingColumnId === column.id ? "Saving..." : "Save"}
                                    </button>
                                  </div>
                                ) : (
                                  <div className="text-sm text-gray-600">
                                    {column.description || "No description yet."}
                                  </div>
                                )}
                              </div>

                              <div>
                                <div className="mb-1 flex items-center gap-2">
                                  <div className="text-xs font-semibold text-gray-500">
                                    Sample Values
                                  </div>
                                  {column.masked && (
                                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">
                                      Masked for Viewers
                                    </span>
                                  )}
                                </div>
                                {sampleValues.length === 0 ? (
                                  <div className="text-sm text-gray-500">No samples recorded.</div>
                                ) : (
                                  <div className="flex flex-wrap gap-1.5">
                                    {sampleValues.map((value, index) => (
                                      <span
                                        key={index}
                                        className={`rounded px-2 py-1 font-mono text-xs ${
                                          column.masked
                                            ? "bg-amber-50 text-amber-700"
                                            : "bg-gray-100 text-gray-700"
                                        }`}
                                      >
                                        {value}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {canMaskColumns && (
                                  <button
                                    onClick={() => handleToggleColumnMasking(column)}
                                    disabled={savingMaskColumnId === column.id}
                                    className="mt-2 rounded-lg border px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                                  >
                                    {savingMaskColumnId === column.id
                                      ? "Saving..."
                                      : column.masked
                                        ? "Unmask for Viewers"
                                        : "Mask from Viewers"}
                                  </button>
                                )}
                              </div>

                              <div>
                                <div className="mb-1 text-xs font-semibold text-gray-500">
                                  Column Lineage
                                </div>
                                {upstreamMappings.length === 0 && downstreamMappings.length === 0 ? (
                                  <div className="text-sm text-gray-500">
                                    No column-level lineage recorded.
                                  </div>
                                ) : (
                                  <div className="space-y-1.5">
                                    {upstreamMappings.map((edge) => {
                                      const upstreamDataset = allDatasets.find(
                                        (d) => d.id === edge.upstream_dataset_id
                                      );
                                      return (
                                        <div key={edge.id} className="text-xs text-gray-600">
                                          <span className="font-mono bg-gray-100 rounded px-1.5 py-0.5">
                                            {edge.upstream_column_name}
                                          </span>{" "}
                                          &larr;{" "}
                                          {upstreamDataset
                                            ? `${upstreamDataset.schema_name}.${upstreamDataset.name}`
                                            : edge.upstream_dataset_id}
                                        </div>
                                      );
                                    })}
                                    {downstreamMappings.map((edge) => {
                                      const downstreamDataset = allDatasets.find(
                                        (d) => d.id === edge.downstream_dataset_id
                                      );
                                      return (
                                        <div key={edge.id} className="text-xs text-gray-600">
                                          &rarr;{" "}
                                          {downstreamDataset
                                            ? `${downstreamDataset.schema_name}.${downstreamDataset.name}`
                                            : edge.downstream_dataset_id}{" "}
                                          <span className="font-mono bg-gray-100 rounded px-1.5 py-0.5">
                                            {edge.downstream_column_name}
                                          </span>
                                        </div>
                                      );
                                    })}
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {columns.length === 0 && !columnErrorMessage && (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-gray-500">
                      No columns discovered yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "lineage" && (
        <div>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 mb-6">
            <div className="bg-white rounded-xl p-6 shadow">
              <h3 className="mb-3 text-sm font-semibold text-gray-500">
                Depends on (upstream)
              </h3>
              <div className="space-y-2">
                {dependencies.map((edge) => {
                  const upstream = allDatasets.find((d) => d.id === edge.upstream_dataset_id);
                  return (
                    <LineageEdgeCard
                      key={edge.id}
                      edge={edge}
                      href={`/datasets/${edge.upstream_dataset_id}`}
                      label={upstream ? `${upstream.schema_name}.${upstream.name}` : edge.upstream_dataset_id}
                      canEdit={canEditGovernance}
                    />
                  );
                })}
                {dependencies.length === 0 && (
                  <div className="text-sm text-gray-500">Nothing upstream of this dataset.</div>
                )}
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 shadow">
              <h3 className="mb-3 text-sm font-semibold text-gray-500">
                Would be affected (downstream)
              </h3>
              <div className="space-y-2">
                {impact.map((edge) => {
                  const downstream = allDatasets.find((d) => d.id === edge.downstream_dataset_id);
                  return (
                    <LineageEdgeCard
                      key={edge.id}
                      edge={edge}
                      href={`/datasets/${edge.downstream_dataset_id}`}
                      label={
                        downstream
                          ? `${downstream.schema_name}.${downstream.name}`
                          : edge.downstream_dataset_id
                      }
                      canEdit={canEditGovernance}
                    />
                  );
                })}
                {impact.length === 0 && (
                  <div className="text-sm text-gray-500">Nothing downstream of this dataset.</div>
                )}
              </div>
            </div>
          </div>

          {(columnLineageUpstream.length > 0 || columnLineageDownstream.length > 0) && (
            <div className="bg-white rounded-xl p-6 shadow mb-6">
              <h3 className="mb-3 text-sm font-semibold text-gray-500">
                Column-Level Lineage
              </h3>
              <div className="space-y-2">
                {columnLineageUpstream.map((edge) => {
                  const upstream = allDatasets.find((d) => d.id === edge.upstream_dataset_id);
                  return (
                    <div
                      key={edge.id}
                      className="flex flex-wrap items-center gap-2 text-sm border rounded-lg px-3 py-2"
                    >
                      <span className="text-gray-500">
                        {upstream ? `${upstream.schema_name}.${upstream.name}` : edge.upstream_dataset_id}
                      </span>
                      <span className="font-mono text-xs bg-gray-100 rounded px-1.5 py-0.5">
                        {edge.upstream_column_name}
                      </span>
                      <span className="text-gray-400">→</span>
                      <span className="font-mono text-xs bg-gray-100 rounded px-1.5 py-0.5">
                        {edge.downstream_column_name}
                      </span>
                      {edge.transformation_type && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                          {edge.transformation_type}
                        </span>
                      )}
                      {edge.transformation_description && (
                        <span className="text-xs text-gray-500 w-full">
                          {edge.transformation_description}
                        </span>
                      )}
                    </div>
                  );
                })}
                {columnLineageDownstream.map((edge) => {
                  const downstream = allDatasets.find((d) => d.id === edge.downstream_dataset_id);
                  return (
                    <div
                      key={edge.id}
                      className="flex flex-wrap items-center gap-2 text-sm border rounded-lg px-3 py-2"
                    >
                      <span className="font-mono text-xs bg-gray-100 rounded px-1.5 py-0.5">
                        {edge.upstream_column_name}
                      </span>
                      <span className="text-gray-400">→</span>
                      <span className="font-mono text-xs bg-gray-100 rounded px-1.5 py-0.5">
                        {edge.downstream_column_name}
                      </span>
                      <span className="text-gray-500">
                        {downstream
                          ? `${downstream.schema_name}.${downstream.name}`
                          : edge.downstream_dataset_id}
                      </span>
                      {edge.transformation_type && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                          {edge.transformation_type}
                        </span>
                      )}
                      {edge.transformation_description && (
                        <span className="text-xs text-gray-500 w-full">
                          {edge.transformation_description}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {canEditGovernance && allDatasets.length > 0 && (
            <CreateLineageForm
              datasets={allDatasets}
              currentDataset={dataset}
              onCreated={fetchLineageForDataset}
            />
          )}
        </div>
      )}

      {activeTab === "governance" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl p-6 shadow">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Ownership, Classification &amp; Privacy</h2>
              {canEditGovernance && !governanceEditMode && (
                <button
                  onClick={() => setGovernanceEditMode(true)}
                  className="text-sm rounded-lg border px-3 py-1.5 hover:bg-gray-50"
                >
                  Edit
                </button>
              )}
            </div>

            {!governanceEditMode && (
              <div className="grid grid-cols-1 gap-6 md:grid-cols-2 text-sm">
                <div className="space-y-3">
                  <div>
                    <div className="text-gray-500">Owner</div>
                    <div className="mt-1">{dataset.owner || "Not set"}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Steward</div>
                    <div className="mt-1">{dataset.steward || "Not set"}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Domain</div>
                    <div className="mt-1">{dataset.domain || "Not set"}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Tags</div>
                    <div className="mt-1">{dataset.tags || "None"}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">System Role</div>
                    <div className="mt-1">
                      {dataset.system_role ? (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            dataset.system_role === "SYSTEM_OF_RECORD"
                              ? "bg-blue-100 text-blue-700"
                              : "bg-purple-100 text-purple-700"
                          }`}
                        >
                          {dataset.system_role === "SYSTEM_OF_RECORD"
                            ? "System of Record"
                            : "System of Reference"}
                        </span>
                      ) : (
                        "Not set"
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="text-gray-500">Data Category</div>
                    <div className="mt-1">
                      {dataset.data_category ? (
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium capitalize">
                          {dataset.data_category.toLowerCase()}
                        </span>
                      ) : (
                        "Not classified"
                      )}
                    </div>
                  </div>
                </div>
                <div className="space-y-3">
                  <div>
                    <div className="text-gray-500">Purpose</div>
                    <div className="mt-1">{scorecard?.purpose || "Not documented"}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Consent Status</div>
                    <div className="mt-1">{scorecard?.consent_status || "NOT_ASSESSED"}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">Retention</div>
                    <div className="mt-1">
                      {scorecard?.retention_status}
                      {scorecard?.retention_period_days
                        ? ` · ${scorecard.retention_period_days} days`
                        : ""}
                    </div>
                  </div>
                  {scorecard?.retention_notes && (
                    <div>
                      <div className="text-gray-500">Retention Notes</div>
                      <div className="mt-1">{scorecard.retention_notes}</div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {governanceEditMode && (
              <div className="space-y-6">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Owner</label>
                    <input
                      type="text"
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={form.owner ?? ""}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, owner: event.target.value }))
                      }
                    />
                  </div>

                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Steward</label>
                    <input
                      type="text"
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={form.steward ?? ""}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, steward: event.target.value }))
                      }
                    />
                  </div>

                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Domain</label>
                    <input
                      type="text"
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      placeholder="e.g. Sales, Finance"
                      value={form.domain ?? ""}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, domain: event.target.value }))
                      }
                    />
                  </div>

                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Tags</label>
                    <input
                      type="text"
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      placeholder="comma,separated,tags"
                      value={form.tags ?? ""}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, tags: event.target.value }))
                      }
                    />
                  </div>

                  <div>
                    <label className="text-sm text-gray-500 block mb-1">System Role</label>
                    <select
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={form.system_role ?? ""}
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          system_role: (event.target.value || null) as DatasetGovernanceUpdate["system_role"],
                        }))
                      }
                    >
                      <option value="">Not set</option>
                      <option value="SYSTEM_OF_RECORD">System of Record</option>
                      <option value="SYSTEM_OF_REFERENCE">System of Reference</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Data Category</label>
                    <select
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={form.data_category ?? ""}
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          data_category: (event.target.value || null) as DatasetGovernanceUpdate["data_category"],
                        }))
                      }
                    >
                      <option value="">Not classified</option>
                      <option value="MASTER">Master</option>
                      <option value="REFERENCE">Reference</option>
                      <option value="TRANSACTIONAL">Transactional</option>
                      <option value="ANALYTICAL">Analytical</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Certification</label>
                    <select
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={form.certification ?? "DRAFT"}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, certification: event.target.value }))
                      }
                    >
                      <option value="DRAFT">DRAFT</option>
                      <option value="IN_REVIEW">IN_REVIEW</option>
                      <option value="DEPRECATED">DEPRECATED</option>
                    </select>
                    <div className="text-xs text-gray-500 mt-1">
                      VERIFIED can only be reached through certification review below.
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-3 border-t pt-6">
                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Purpose</label>
                    <input
                      type="text"
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      placeholder="e.g. Order fulfillment and customer support"
                      value={form.purpose ?? ""}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, purpose: event.target.value }))
                      }
                    />
                  </div>

                  <div>
                    <label className="text-sm text-gray-500 block mb-1">Consent Status</label>
                    <select
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={form.consent_status ?? "NOT_ASSESSED"}
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          consent_status: event.target.value as ConsentStatus,
                        }))
                      }
                    >
                      {CONSENT_STATUS_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-sm text-gray-500 block mb-1">
                      Retention Period (days)
                    </label>
                    <input
                      type="number"
                      min={0}
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={
                        form.retention_period_days === undefined ||
                        form.retention_period_days === null
                          ? ""
                          : form.retention_period_days
                      }
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          retention_period_days:
                            event.target.value === "" ? undefined : Number(event.target.value),
                        }))
                      }
                    />
                  </div>

                  <div className="md:col-span-3">
                    <label className="text-sm text-gray-500 block mb-1">Retention Notes</label>
                    <textarea
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      rows={2}
                      value={form.retention_notes ?? ""}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, retention_notes: event.target.value }))
                      }
                    />
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={handleSaveGovernance}
                    disabled={saving}
                    className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                  <button
                    onClick={cancelGovernanceEdit}
                    disabled={saving}
                    className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  {saveMessage && <span className="text-sm text-gray-500">{saveMessage}</span>}
                </div>
              </div>
            )}
          </div>

          <div className="bg-white rounded-xl p-6 shadow">
            <h2 className="text-xl font-semibold mb-4">Data Quality</h2>

            {dataQualityMessage && <div className="text-gray-500">{dataQualityMessage}</div>}

            {dataQuality && (
              <div className="grid grid-cols-2 sm:grid-cols-6 gap-4 text-sm items-end">
                <div>
                  <div className="text-gray-500">Overall</div>
                  <div className="text-2xl font-bold mt-1">
                    {Math.round(dataQuality.overall_score ?? 0)}
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">Completeness</div>
                  <div className="font-semibold mt-1">
                    {Math.round(dataQuality.completeness ?? 0)}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">Uniqueness</div>
                  <div className="font-semibold mt-1">
                    {Math.round(dataQuality.uniqueness ?? 0)}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">Validity</div>
                  <div className="font-semibold mt-1">
                    {Math.round(dataQuality.validity ?? 0)}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">Consistency</div>
                  <div className="font-semibold mt-1">
                    {Math.round(dataQuality.consistency ?? 0)}%
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">Freshness</div>
                  <div className="font-semibold mt-1">
                    {Math.round(dataQuality.freshness ?? 0)}%
                  </div>
                </div>
              </div>
            )}
          </div>

          <CertificationWorkflowPanel
            datasetId={dataset.id}
            certification={dataset.certification}
            pendingRequestId={dataset.pending_certification_request_id}
            canRequest={canEditGovernance}
            canApprove={user?.role === "admin" || user?.role === "data_owner"}
          />

          <DataContractPanel datasetId={dataset.id} canEdit={canEditGovernance} />
        </div>
      )}

      {activeTab === "discussion" && <DatasetDiscussionPanel datasetId={dataset.id} />}
    </main>
  );
}
