"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import {
  controlStatusBadgeClasses,
  riskLevelBadgeClasses as levelBadgeClasses,
  riskStatusBadgeClasses,
} from "../../utils/badgeStyles";
import type {
  BusinessProcess,
  Control,
  ControlCreate,
  ControlStatus,
  ControlType,
  Dataset,
  Risk,
  RiskCategory,
  RiskCreate,
  RiskDetail,
  RiskLevel,
  RiskStatus,
  TeamMember,
} from "../../types/metadata";

type Tab = "risks" | "controls";

const CATEGORIES: RiskCategory[] = [
  "PRIVACY",
  "SECURITY",
  "OPERATIONAL",
  "COMPLIANCE",
  "DATA_QUALITY",
  "OTHER",
];

const LEVELS: RiskLevel[] = ["LOW", "MEDIUM", "HIGH"];

const RISK_STATUSES: RiskStatus[] = ["OPEN", "MITIGATED", "ACCEPTED", "CLOSED"];

const CONTROL_TYPES: ControlType[] = ["PREVENTIVE", "DETECTIVE", "CORRECTIVE"];

const CONTROL_STATUSES: ControlStatus[] = ["NOT_TESTED", "EFFECTIVE", "INEFFECTIVE"];

const EMPTY_NEW_RISK: RiskCreate = {
  title: "",
  description: "",
  category: "OTHER",
  likelihood: "MEDIUM",
  impact: "MEDIUM",
};

const EMPTY_NEW_CONTROL: ControlCreate = {
  name: "",
  description: "",
  control_type: "PREVENTIVE",
};

export default function RisksPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [tab, setTab] = useState<Tab>("risks");
  const [risks, setRisks] = useState<Risk[]>([]);
  const [controls, setControls] = useState<Control[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [processes, setProcesses] = useState<BusinessProcess[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canEdit = user?.role === "admin" || user?.role === "steward";

  const [showNewRiskForm, setShowNewRiskForm] = useState(false);
  const [newRisk, setNewRisk] = useState<RiskCreate>(EMPTY_NEW_RISK);
  const [creatingRisk, setCreatingRisk] = useState(false);

  const [showNewControlForm, setShowNewControlForm] = useState(false);
  const [newControl, setNewControl] = useState<ControlCreate>(EMPTY_NEW_CONTROL);
  const [creatingControl, setCreatingControl] = useState(false);

  const [expandedRiskId, setExpandedRiskId] = useState<string | null>(null);
  const [riskDetail, setRiskDetail] = useState<RiskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [linkDatasetId, setLinkDatasetId] = useState("");
  const [linkProcessId, setLinkProcessId] = useState("");
  const [linkControlId, setLinkControlId] = useState("");

  async function fetchRisks() {
    try {
      const response = await api.get<Risk[]>("/api/risks");
      setRisks(response.data);
    } catch (error) {
      console.error(error);
      setErrorMessage("Unable to load risks. Please make sure the backend is running.");
    }
  }

  async function fetchControls() {
    try {
      const response = await api.get<Control[]>("/api/controls");
      setControls(response.data);
    } catch (error) {
      console.error(error);
    }
  }

  useEffect(() => {
    if (!user) return;

    async function loadAll() {
      await Promise.all([fetchRisks(), fetchControls()]);

      try {
        const [datasetsResponse, processesResponse, teamResponse] = await Promise.all([
          api.get<Dataset[]>("/api/datasets"),
          api.get<BusinessProcess[]>("/api/business-processes"),
          api.get<TeamMember[]>("/api/users"),
        ]);
        setDatasets(datasetsResponse.data);
        setProcesses(processesResponse.data);
        setTeamMembers(teamResponse.data);
      } catch (error) {
        console.error(error);
      }
    }

    loadAll();
  }, [user]);

  async function loadRiskDetail(riskId: string) {
    setDetailLoading(true);
    try {
      const response = await api.get<RiskDetail>(`/api/risks/${riskId}`);
      setRiskDetail(response.data);
    } catch (error) {
      console.error(error);
    } finally {
      setDetailLoading(false);
    }
  }

  async function toggleExpanded(risk: Risk) {
    if (expandedRiskId === risk.id) {
      setExpandedRiskId(null);
      setRiskDetail(null);
      return;
    }

    setExpandedRiskId(risk.id);
    setLinkDatasetId("");
    setLinkProcessId("");
    setLinkControlId("");
    await loadRiskDetail(risk.id);
  }

  async function handleCreateRisk() {
    if (!newRisk.title.trim()) return;

    setCreatingRisk(true);
    try {
      await api.post("/api/risks", {
        ...newRisk,
        description: newRisk.description || undefined,
        owner_user_id: newRisk.owner_user_id || undefined,
      });
      setNewRisk(EMPTY_NEW_RISK);
      setShowNewRiskForm(false);
      await fetchRisks();
    } catch (error) {
      console.error(error);
      alert("Unable to create risk.");
    } finally {
      setCreatingRisk(false);
    }
  }

  async function handleCreateControl() {
    if (!newControl.name.trim()) return;

    setCreatingControl(true);
    try {
      await api.post("/api/controls", {
        ...newControl,
        description: newControl.description || undefined,
        owner_user_id: newControl.owner_user_id || undefined,
      });
      setNewControl(EMPTY_NEW_CONTROL);
      setShowNewControlForm(false);
      await fetchControls();
    } catch (error) {
      console.error(error);
      alert("Unable to create control.");
    } finally {
      setCreatingControl(false);
    }
  }

  async function updateRiskStatus(riskId: string, status: RiskStatus) {
    try {
      await api.patch(`/api/risks/${riskId}`, { status });
      await fetchRisks();
      if (expandedRiskId === riskId) await loadRiskDetail(riskId);
    } catch (error) {
      console.error(error);
    }
  }

  async function updateControlStatus(controlId: string, status: ControlStatus) {
    try {
      await api.patch(`/api/controls/${controlId}`, { status, mark_tested_now: true });
      await fetchControls();
      if (expandedRiskId) await loadRiskDetail(expandedRiskId);
    } catch (error) {
      console.error(error);
    }
  }

  async function linkDataset(riskId: string) {
    if (!linkDatasetId) return;
    try {
      await api.post(`/api/risks/${riskId}/datasets`, { dataset_id: linkDatasetId });
      setLinkDatasetId("");
      await loadRiskDetail(riskId);
      await fetchRisks();
    } catch (error) {
      console.error(error);
    }
  }

  async function unlinkDataset(riskId: string, datasetId: string) {
    try {
      await api.delete(`/api/risks/${riskId}/datasets/${datasetId}`);
      await loadRiskDetail(riskId);
      await fetchRisks();
    } catch (error) {
      console.error(error);
    }
  }

  async function linkProcess(riskId: string) {
    if (!linkProcessId) return;
    try {
      await api.post(`/api/risks/${riskId}/processes`, { process_id: linkProcessId });
      setLinkProcessId("");
      await loadRiskDetail(riskId);
      await fetchRisks();
    } catch (error) {
      console.error(error);
    }
  }

  async function unlinkProcess(riskId: string, processId: string) {
    try {
      await api.delete(`/api/risks/${riskId}/processes/${processId}`);
      await loadRiskDetail(riskId);
      await fetchRisks();
    } catch (error) {
      console.error(error);
    }
  }

  async function linkControl(riskId: string) {
    if (!linkControlId) return;
    try {
      await api.post(`/api/risks/${riskId}/controls`, { control_id: linkControlId });
      setLinkControlId("");
      await loadRiskDetail(riskId);
      await fetchRisks();
    } catch (error) {
      console.error(error);
    }
  }

  async function unlinkControl(riskId: string, controlId: string) {
    try {
      await api.delete(`/api/risks/${riskId}/controls/${controlId}`);
      await loadRiskDetail(riskId);
      await fetchRisks();
    } catch (error) {
      console.error(error);
    }
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  const linkableDatasets = riskDetail
    ? datasets.filter((d) => !riskDetail.linked_datasets.some((ld) => ld.id === d.id))
    : datasets;
  const linkableProcesses = riskDetail
    ? processes.filter((p) => !riskDetail.linked_processes.some((lp) => lp.id === p.id))
    : processes;
  const linkableControls = riskDetail
    ? controls.filter((c) => !riskDetail.linked_controls.some((lc) => lc.id === c.id))
    : controls;

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-4xl font-bold">Risks &amp; Controls</h1>
          <p className="mt-2 max-w-2xl text-gray-600">
            A lightweight risk register linked to your datasets and processes, plus
            a reusable control library. Inherent risk comes from likelihood &times;
            impact; residual risk accounts for any linked controls that are actually
            marked effective.
          </p>
        </div>
      </div>

      <div className="mb-6 flex rounded-lg border bg-white text-sm overflow-hidden w-fit">
        <button
          onClick={() => setTab("risks")}
          className={`px-4 py-2 ${tab === "risks" ? "bg-black text-white" : "hover:bg-gray-50"}`}
        >
          Risk Register
        </button>
        <button
          onClick={() => setTab("controls")}
          className={`px-4 py-2 ${tab === "controls" ? "bg-black text-white" : "hover:bg-gray-50"}`}
        >
          Control Library
        </button>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {tab === "risks" && (
        <div>
          {canEdit && (
            <div className="mb-4">
              <button
                onClick={() => setShowNewRiskForm((v) => !v)}
                className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800"
              >
                {showNewRiskForm ? "Cancel" : "New Risk"}
              </button>
            </div>
          )}

          {showNewRiskForm && (
            <div className="mb-6 space-y-3 rounded-xl bg-white p-6 shadow">
              <input
                type="text"
                placeholder="Title (e.g. Unmasked PII in downstream reporting)"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newRisk.title}
                onChange={(e) => setNewRisk((prev) => ({ ...prev, title: e.target.value }))}
              />
              <textarea
                placeholder="Description (optional)"
                rows={2}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newRisk.description}
                onChange={(e) => setNewRisk((prev) => ({ ...prev, description: e.target.value }))}
              />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <select
                  className="rounded-lg border px-3 py-2 text-sm"
                  value={newRisk.category}
                  onChange={(e) =>
                    setNewRisk((prev) => ({ ...prev, category: e.target.value as RiskCategory }))
                  }
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c.replace("_", " ")}
                    </option>
                  ))}
                </select>
                <select
                  className="rounded-lg border px-3 py-2 text-sm"
                  value={newRisk.likelihood}
                  onChange={(e) =>
                    setNewRisk((prev) => ({ ...prev, likelihood: e.target.value as RiskLevel }))
                  }
                >
                  {LEVELS.map((l) => (
                    <option key={l} value={l}>
                      Likelihood: {l}
                    </option>
                  ))}
                </select>
                <select
                  className="rounded-lg border px-3 py-2 text-sm"
                  value={newRisk.impact}
                  onChange={(e) =>
                    setNewRisk((prev) => ({ ...prev, impact: e.target.value as RiskLevel }))
                  }
                >
                  {LEVELS.map((l) => (
                    <option key={l} value={l}>
                      Impact: {l}
                    </option>
                  ))}
                </select>
              </div>
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newRisk.owner_user_id ?? ""}
                onChange={(e) => setNewRisk((prev) => ({ ...prev, owner_user_id: e.target.value }))}
              >
                <option value="">No owner assigned</option>
                {teamMembers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.email} ({m.role.replace("_", " ")})
                  </option>
                ))}
              </select>
              <button
                onClick={handleCreateRisk}
                disabled={creatingRisk}
                className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {creatingRisk ? "Creating..." : "Create Risk"}
              </button>
            </div>
          )}

          <div className="space-y-4">
            {risks.map((risk) => (
              <div key={risk.id} className="rounded-xl bg-white p-6 shadow">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700">
                        {risk.category.replace("_", " ")}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${riskStatusBadgeClasses(
                          risk.status
                        )}`}
                      >
                        {risk.status}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${levelBadgeClasses(
                          risk.inherent_level
                        )}`}
                        title="Inherent risk (likelihood x impact, before controls)"
                      >
                        Inherent: {risk.inherent_level}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${levelBadgeClasses(
                          risk.residual_level
                        )}`}
                        title={`Residual risk after ${risk.effective_control_count} effective control(s)`}
                      >
                        Residual: {risk.residual_level}
                      </span>
                    </div>
                    <div className="text-lg font-semibold">{risk.title}</div>
                    {risk.description && (
                      <div className="mt-1 text-sm text-gray-600">{risk.description}</div>
                    )}
                    <div className="mt-2 text-xs text-gray-500">
                      {risk.owner_email ? `Owner: ${risk.owner_email}` : "No owner assigned"}
                      {" · "}
                      {risk.dataset_count} dataset{risk.dataset_count === 1 ? "" : "s"}
                      {" · "}
                      {risk.process_count} process{risk.process_count === 1 ? "" : "es"}
                      {" · "}
                      {risk.control_count} control{risk.control_count === 1 ? "" : "s"}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    {canEdit && (
                      <select
                        className="rounded-lg border px-2 py-1.5 text-xs"
                        value={risk.status}
                        onChange={(e) => updateRiskStatus(risk.id, e.target.value as RiskStatus)}
                      >
                        {RISK_STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    )}
                    <button
                      onClick={() => toggleExpanded(risk)}
                      className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50"
                    >
                      {expandedRiskId === risk.id ? "Hide details" : "Manage links"}
                    </button>
                  </div>
                </div>

                {expandedRiskId === risk.id && (
                  <div className="mt-4 space-y-4 border-t pt-4">
                    {detailLoading && <div className="text-sm text-gray-500">Loading...</div>}

                    {riskDetail && riskDetail.id === risk.id && (
                      <>
                        <div>
                          <div className="mb-1 text-xs font-semibold text-gray-500">Datasets</div>
                          <div className="flex flex-wrap gap-2">
                            {riskDetail.linked_datasets.map((d) => (
                              <span
                                key={d.id}
                                className="flex items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700"
                              >
                                <Link href={`/datasets/${d.id}`} className="hover:underline">
                                  {d.schema_name}.{d.name}
                                </Link>
                                {canEdit && (
                                  <button
                                    onClick={() => unlinkDataset(risk.id, d.id)}
                                    className="text-gray-400 hover:text-red-600"
                                  >
                                    &times;
                                  </button>
                                )}
                              </span>
                            ))}
                            {riskDetail.linked_datasets.length === 0 && (
                              <span className="text-xs text-gray-400">None linked</span>
                            )}
                          </div>
                          {canEdit && (
                            <div className="mt-2 flex gap-2">
                              <select
                                className="rounded-lg border px-2 py-1.5 text-xs"
                                value={linkDatasetId}
                                onChange={(e) => setLinkDatasetId(e.target.value)}
                              >
                                <option value="">Link a dataset...</option>
                                {linkableDatasets.map((d) => (
                                  <option key={d.id} value={d.id}>
                                    {d.schema_name}.{d.name}
                                  </option>
                                ))}
                              </select>
                              <button
                                onClick={() => linkDataset(risk.id)}
                                disabled={!linkDatasetId}
                                className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-50"
                              >
                                Add
                              </button>
                            </div>
                          )}
                        </div>

                        <div>
                          <div className="mb-1 text-xs font-semibold text-gray-500">Processes</div>
                          <div className="flex flex-wrap gap-2">
                            {riskDetail.linked_processes.map((p) => (
                              <span
                                key={p.id}
                                className="flex items-center gap-1 rounded-full bg-blue-50 px-3 py-1 text-xs text-blue-700"
                              >
                                {p.name}
                                {canEdit && (
                                  <button
                                    onClick={() => unlinkProcess(risk.id, p.id)}
                                    className="text-blue-400 hover:text-red-600"
                                  >
                                    &times;
                                  </button>
                                )}
                              </span>
                            ))}
                            {riskDetail.linked_processes.length === 0 && (
                              <span className="text-xs text-gray-400">None linked</span>
                            )}
                          </div>
                          {canEdit && (
                            <div className="mt-2 flex gap-2">
                              <select
                                className="rounded-lg border px-2 py-1.5 text-xs"
                                value={linkProcessId}
                                onChange={(e) => setLinkProcessId(e.target.value)}
                              >
                                <option value="">Link a process...</option>
                                {linkableProcesses.map((p) => (
                                  <option key={p.id} value={p.id}>
                                    {p.name}
                                  </option>
                                ))}
                              </select>
                              <button
                                onClick={() => linkProcess(risk.id)}
                                disabled={!linkProcessId}
                                className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-50"
                              >
                                Add
                              </button>
                            </div>
                          )}
                        </div>

                        <div>
                          <div className="mb-1 text-xs font-semibold text-gray-500">Controls</div>
                          <div className="flex flex-wrap gap-2">
                            {riskDetail.linked_controls.map((c) => (
                              <span
                                key={c.id}
                                className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs ${controlStatusBadgeClasses(
                                  c.status
                                )}`}
                              >
                                {c.name}
                                {canEdit && (
                                  <button
                                    onClick={() => unlinkControl(risk.id, c.id)}
                                    className="hover:text-red-600"
                                  >
                                    &times;
                                  </button>
                                )}
                              </span>
                            ))}
                            {riskDetail.linked_controls.length === 0 && (
                              <span className="text-xs text-gray-400">None linked</span>
                            )}
                          </div>
                          {canEdit && (
                            <div className="mt-2 flex gap-2">
                              <select
                                className="rounded-lg border px-2 py-1.5 text-xs"
                                value={linkControlId}
                                onChange={(e) => setLinkControlId(e.target.value)}
                              >
                                <option value="">Link a control...</option>
                                {linkableControls.map((c) => (
                                  <option key={c.id} value={c.id}>
                                    {c.name} ({c.status})
                                  </option>
                                ))}
                              </select>
                              <button
                                onClick={() => linkControl(risk.id)}
                                disabled={!linkControlId}
                                className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50 disabled:opacity-50"
                              >
                                Add
                              </button>
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}

            {risks.length === 0 && !showNewRiskForm && (
              <div className="rounded-xl border border-dashed bg-white p-8 text-center text-gray-500">
                No risks logged yet.
                {canEdit ? " Click \"New Risk\" to add the first one." : " Ask an admin or steward to add one."}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "controls" && (
        <div>
          {canEdit && (
            <div className="mb-4">
              <button
                onClick={() => setShowNewControlForm((v) => !v)}
                className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800"
              >
                {showNewControlForm ? "Cancel" : "New Control"}
              </button>
            </div>
          )}

          {showNewControlForm && (
            <div className="mb-6 space-y-3 rounded-xl bg-white p-6 shadow">
              <input
                type="text"
                placeholder="Name (e.g. Quarterly access review)"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newControl.name}
                onChange={(e) => setNewControl((prev) => ({ ...prev, name: e.target.value }))}
              />
              <textarea
                placeholder="Description (optional)"
                rows={2}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newControl.description}
                onChange={(e) =>
                  setNewControl((prev) => ({ ...prev, description: e.target.value }))
                }
              />
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newControl.control_type}
                onChange={(e) =>
                  setNewControl((prev) => ({ ...prev, control_type: e.target.value as ControlType }))
                }
              >
                {CONTROL_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newControl.owner_user_id ?? ""}
                onChange={(e) =>
                  setNewControl((prev) => ({ ...prev, owner_user_id: e.target.value }))
                }
              >
                <option value="">No owner assigned</option>
                {teamMembers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.email} ({m.role.replace("_", " ")})
                  </option>
                ))}
              </select>
              <button
                onClick={handleCreateControl}
                disabled={creatingControl}
                className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {creatingControl ? "Creating..." : "Create Control"}
              </button>
            </div>
          )}

          <div className="space-y-3">
            {controls.map((control) => (
              <div key={control.id} className="rounded-xl bg-white p-5 shadow">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="mb-1 flex items-center gap-2">
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700">
                        {control.control_type}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${controlStatusBadgeClasses(
                          control.status
                        )}`}
                      >
                        {control.status.replace("_", " ")}
                      </span>
                    </div>
                    <div className="font-semibold">{control.name}</div>
                    {control.description && (
                      <div className="mt-1 text-sm text-gray-600">{control.description}</div>
                    )}
                    <div className="mt-2 text-xs text-gray-500">
                      {control.owner_email ? `Owner: ${control.owner_email}` : "No owner assigned"}
                      {" · "}
                      {control.risk_count} risk{control.risk_count === 1 ? "" : "s"} mitigated
                      {control.last_tested_at &&
                        ` · last tested ${new Date(control.last_tested_at).toLocaleDateString()}`}
                    </div>
                  </div>

                  {canEdit && (
                    <select
                      className="shrink-0 rounded-lg border px-2 py-1.5 text-xs"
                      value={control.status}
                      onChange={(e) =>
                        updateControlStatus(control.id, e.target.value as ControlStatus)
                      }
                    >
                      {CONTROL_STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {s.replace("_", " ")}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            ))}

            {controls.length === 0 && !showNewControlForm && (
              <div className="rounded-xl border border-dashed bg-white p-8 text-center text-gray-500">
                No controls in the library yet.
                {canEdit
                  ? " Click \"New Control\" to add the first one."
                  : " Ask an admin or steward to add one."}
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
