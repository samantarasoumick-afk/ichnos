"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import DataQualityBars from "./DataQualityBars";
import MiniLineageDiagram from "./MiniLineageDiagram";
import api from "../services/api";
import type {
  BusinessGlossaryTerm,
  BusinessProcess,
  DataContract,
  DataQuality,
  Dataset,
  DatasetColumn,
  EffectiveQuality,
  GlossaryTermLink,
  Lineage,
  Risk,
} from "../types/metadata";

type Props = {
  dataset: Dataset;
  columns: DatasetColumn[];
  dataQuality: DataQuality | null;
  effectiveQuality?: EffectiveQuality | null;
  dependencies: Lineage[];
  impact: Lineage[];
  allDatasets: Dataset[];
  canEdit: boolean;
};

function contractBadgeClasses(status: string | undefined) {
  if (status === "COMPLIANT") return "bg-green-100 text-green-700";
  if (status === "BREACHED") return "bg-red-100 text-red-700";
  if (status === "PENDING_EVALUATION") return "bg-yellow-100 text-yellow-700";
  return "bg-gray-100 text-gray-500"; // NO_CONTRACT
}

function riskLevelBadgeClasses(level: string) {
  if (level === "HIGH") return "bg-red-100 text-red-700";
  if (level === "MEDIUM") return "bg-yellow-100 text-yellow-700";
  return "bg-green-100 text-green-700";
}

export default function BusinessViewPanel({
  dataset,
  columns,
  dataQuality,
  effectiveQuality,
  dependencies,
  impact,
  allDatasets,
  canEdit,
}: Props) {
  const [termLinks, setTermLinks] = useState<GlossaryTermLink[]>([]);
  const [allTerms, setAllTerms] = useState<BusinessGlossaryTerm[]>([]);
  const [processLinks, setProcessLinks] = useState<BusinessProcess[]>([]);
  const [allProcesses, setAllProcesses] = useState<BusinessProcess[]>([]);
  const [contracts, setContracts] = useState<DataContract[]>([]);
  const [risks, setRisks] = useState<Risk[]>([]);

  const [selectedTermId, setSelectedTermId] = useState("");
  const [selectedColumnId, setSelectedColumnId] = useState("");
  const [linkingTerm, setLinkingTerm] = useState(false);

  const [selectedProcessId, setSelectedProcessId] = useState("");
  const [linkingProcess, setLinkingProcess] = useState(false);

  async function loadTermLinks() {
    try {
      const response = await api.get<GlossaryTermLink[]>(`/api/glossary-links/dataset/${dataset.id}`);
      setTermLinks(response.data);
    } catch (error) {
      console.error(error);
    }
  }

  async function loadProcessLinks() {
    try {
      const response = await api.get<BusinessProcess[]>(`/api/business-processes/dataset/${dataset.id}`);
      setProcessLinks(response.data);
    } catch (error) {
      console.error(error);
    }
  }

  useEffect(() => {
    async function loadAll() {
      try {
        const [
          termLinksResponse,
          allTermsResponse,
          processLinksResponse,
          allProcessesResponse,
          contractsResponse,
          risksResponse,
        ] = await Promise.all([
          api.get<GlossaryTermLink[]>(`/api/glossary-links/dataset/${dataset.id}`),
          api.get<BusinessGlossaryTerm[]>("/api/governance/glossary"),
          api.get<BusinessProcess[]>(`/api/business-processes/dataset/${dataset.id}`),
          api.get<BusinessProcess[]>("/api/business-processes"),
          api.get<DataContract[]>(`/api/data-contracts/dataset/${dataset.id}`),
          api.get<Risk[]>(`/api/risks/dataset/${dataset.id}`),
        ]);
        setTermLinks(termLinksResponse.data);
        setAllTerms(allTermsResponse.data);
        setProcessLinks(processLinksResponse.data);
        setAllProcesses(allProcessesResponse.data);
        setContracts(contractsResponse.data);
        setRisks(risksResponse.data);
      } catch (error) {
        console.error(error);
      }
    }

    loadAll();
  }, [dataset.id]);

  async function linkTerm() {
    if (!selectedTermId) return;

    try {
      setLinkingTerm(true);
      await api.post("/api/glossary-links", {
        term_id: selectedTermId,
        dataset_id: dataset.id,
        column_id: selectedColumnId || undefined,
      });
      setSelectedTermId("");
      setSelectedColumnId("");
      await loadTermLinks();
    } catch (error) {
      console.error(error);
      alert("Unable to link that term - it may already be linked.");
    } finally {
      setLinkingTerm(false);
    }
  }

  async function unlinkTerm(linkId: string) {
    try {
      await api.delete(`/api/glossary-links/${linkId}`);
      setTermLinks((prev) => prev.filter((link) => link.id !== linkId));
    } catch (error) {
      console.error(error);
    }
  }

  async function linkProcess() {
    if (!selectedProcessId) return;

    try {
      setLinkingProcess(true);
      await api.post(`/api/business-processes/${selectedProcessId}/datasets`, {
        dataset_id: dataset.id,
      });
      setSelectedProcessId("");
      await loadProcessLinks();
    } catch (error) {
      console.error(error);
      alert("Unable to link that process - it may already be linked.");
    } finally {
      setLinkingProcess(false);
    }
  }

  async function unlinkProcess(processId: string) {
    try {
      await api.delete(`/api/business-processes/${processId}/datasets/${dataset.id}`);
      setProcessLinks((prev) => prev.filter((process) => process.id !== processId));
    } catch (error) {
      console.error(error);
    }
  }

  const activeContract = contracts.find((c) => c.status === "ACTIVE");
  const linkedTermIds = new Set(termLinks.map((link) => link.term_id));
  const linkableTerms = allTerms.filter((term) => {
    // A term can be linked to this dataset more than once (once for
    // the whole dataset, again for a specific column) - only hide it
    // from the dropdown once it's linked at the dataset level AND no
    // column is selected, to avoid an easy accidental duplicate.
    if (!selectedColumnId && linkedTermIds.has(term.id)) {
      return !termLinks.some((link) => link.term_id === term.id && !link.column_id);
    }
    return true;
  });
  const linkedProcessIds = new Set(processLinks.map((p) => p.id));
  const linkableProcesses = allProcesses.filter((process) => !linkedProcessIds.has(process.id));

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="bg-white rounded-xl p-6 shadow lg:col-span-2">
        <h2 className="text-xl font-semibold mb-1">Business Definitions</h2>
        <p className="text-sm text-gray-500 mb-4">
          What this data means in plain business terms - linked from the Business Glossary.
        </p>

        <div className="space-y-2">
          {termLinks.map((link) => (
            <div key={link.id} className="flex items-start justify-between gap-3 border rounded-lg px-3 py-2">
              <div>
                <div className="text-sm font-semibold">
                  {link.term}
                  {link.column_name && (
                    <span className="ml-2 text-xs font-normal text-gray-500">
                      on column <span className="font-mono">{link.column_name}</span>
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-600 mt-0.5">{link.definition}</div>
              </div>
              {canEdit && (
                <button
                  onClick={() => unlinkTerm(link.id)}
                  className="text-xs text-gray-400 hover:text-red-600 shrink-0"
                >
                  Remove
                </button>
              )}
            </div>
          ))}
          {termLinks.length === 0 && (
            <div className="text-sm text-gray-500">No glossary terms linked to this dataset yet.</div>
          )}
        </div>

        {canEdit && (
          <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t">
            <select
              className="rounded-lg border px-3 py-2 text-sm"
              value={selectedTermId}
              onChange={(e) => setSelectedTermId(e.target.value)}
            >
              <option value="">Select a term to link...</option>
              {linkableTerms.map((term) => (
                <option key={term.id} value={term.id}>
                  {term.term}
                </option>
              ))}
            </select>
            <select
              className="rounded-lg border px-3 py-2 text-sm"
              value={selectedColumnId}
              onChange={(e) => setSelectedColumnId(e.target.value)}
            >
              <option value="">Whole dataset</option>
              {columns.map((column) => (
                <option key={column.id} value={column.id}>
                  Column: {column.name}
                </option>
              ))}
            </select>
            <button
              onClick={linkTerm}
              disabled={!selectedTermId || linkingTerm}
              className="rounded-lg bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {linkingTerm ? "Linking..." : "Link Term"}
            </button>
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl p-6 shadow">
        <h2 className="text-xl font-semibold mb-4">Ownership</h2>
        <div className="space-y-3 text-sm">
          <div>
            <div className="text-gray-500">Owner</div>
            <div className="mt-1 font-medium">{dataset.owner || "Not set"}</div>
          </div>
          <div>
            <div className="text-gray-500">Steward</div>
            <div className="mt-1 font-medium">{dataset.steward || "Not set"}</div>
          </div>
          <div>
            <div className="text-gray-500">Domain</div>
            <div className="mt-1 font-medium">{dataset.domain || "Not set"}</div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl p-6 shadow">
        <h2 className="text-xl font-semibold mb-1">Process</h2>
        <p className="text-sm text-gray-500 mb-4">
          Which end-to-end business activity this data supports.
        </p>

        <div className="flex flex-wrap gap-2">
          {processLinks.map((process) => (
            <div
              key={process.id}
              className="group relative rounded-full bg-blue-50 text-blue-700 text-xs px-3 py-1.5 flex items-center gap-2"
              title={process.description || undefined}
            >
              {process.name}
              {canEdit && (
                <button
                  onClick={() => unlinkProcess(process.id)}
                  className="text-blue-400 hover:text-red-600"
                >
                  ×
                </button>
              )}
            </div>
          ))}
          {processLinks.length === 0 && (
            <div className="text-sm text-gray-500">Not linked to a business process yet.</div>
          )}
        </div>

        {canEdit && (
          <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t">
            <select
              className="rounded-lg border px-3 py-2 text-sm"
              value={selectedProcessId}
              onChange={(e) => setSelectedProcessId(e.target.value)}
            >
              <option value="">Select a process to link...</option>
              {linkableProcesses.map((process) => (
                <option key={process.id} value={process.id}>
                  {process.name}
                </option>
              ))}
            </select>
            <button
              onClick={linkProcess}
              disabled={!selectedProcessId || linkingProcess}
              className="rounded-lg bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {linkingProcess ? "Linking..." : "Link Process"}
            </button>
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl p-6 shadow">
        <h2 className="text-xl font-semibold mb-4">Data Quality</h2>
        <DataQualityBars
          dataQuality={dataQuality}
          effectiveQuality={effectiveQuality}
          allDatasets={allDatasets}
        />
      </div>

      <div className="bg-white rounded-xl p-6 shadow">
        <h2 className="text-xl font-semibold mb-4">Data Contract</h2>
        {activeContract ? (
          <div>
            <span className={`text-xs px-3 py-1 rounded-full ${contractBadgeClasses(activeContract.last_status ?? undefined)}`}>
              {activeContract.last_status || "PENDING_EVALUATION"}
            </span>
            {activeContract.last_status === "BREACHED" && activeContract.last_breach_details && (
              <div className="text-sm text-red-700 mt-3">{activeContract.last_breach_details}</div>
            )}
          </div>
        ) : (
          <div className="text-sm text-gray-500">No active contract on this dataset.</div>
        )}
      </div>

      <div className="bg-white rounded-xl p-6 shadow lg:col-span-2">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-xl font-semibold">Risks</h2>
          <Link href="/risks" className="text-xs text-gray-500 hover:text-black hover:underline">
            View Risk Register &rarr;
          </Link>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Risk entries assessed against this dataset, with residual risk after any
          linked controls.
        </p>
        {risks.length === 0 ? (
          <div className="text-sm text-gray-500">
            No risks logged against this dataset yet.
          </div>
        ) : (
          <div className="space-y-2">
            {risks.map((risk) => (
              <div
                key={risk.id}
                className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
              >
                <div>
                  <div className="text-sm font-semibold">{risk.title}</div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {risk.category.replace("_", " ")} &middot; {risk.status}
                    {risk.owner_email && <> &middot; {risk.owner_email}</>}
                  </div>
                </div>
                <span
                  className={`shrink-0 text-xs px-2 py-1 rounded-full font-medium ${riskLevelBadgeClasses(
                    risk.residual_level
                  )}`}
                >
                  Residual: {risk.residual_level}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl p-6 shadow lg:col-span-2">
        <h2 className="text-xl font-semibold mb-1">Lineage</h2>
        <p className="text-sm text-gray-500 mb-4">
          Depends on <span className="font-semibold">{dependencies.length}</span> upstream dataset
          {dependencies.length === 1 ? "" : "s"}, feeds{" "}
          <span className="font-semibold">{impact.length}</span> downstream dataset
          {impact.length === 1 ? "" : "s"}. Click a node to open that dataset.
        </p>
        <MiniLineageDiagram
          dataset={dataset}
          dependencies={dependencies}
          impact={impact}
          allDatasets={allDatasets}
        />
      </div>
    </div>
  );
}
