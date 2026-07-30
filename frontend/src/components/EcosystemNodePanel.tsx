"use client";

import Link from "next/link";

import type {
  EcosystemDatasetNode,
  EcosystemGraph as EcosystemGraphData,
} from "../types/metadata";
import type { EcosystemSelection } from "./EcosystemGraph";

type Audience = "analyst" | "owner";

type Props = {
  graph: EcosystemGraphData;
  selection: EcosystemSelection | null;
  audience: Audience;
  onClose: () => void;
  onSelectDataset: (dataset: EcosystemDatasetNode) => void;
};

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-gray-100 py-1.5 text-sm last:border-b-0">
      <span className="text-gray-500">{label}</span>
      <span className="text-right font-medium text-gray-900">{value}</span>
    </div>
  );
}

function Sentence({ children }: { children: React.ReactNode }) {
  return <p className="text-sm leading-relaxed text-gray-700">{children}</p>;
}

// Same underlying governance_status/quality_score/etc. fields, worded
// two ways: the analyst view keeps the raw technical vocabulary (the
// enum values, the scores) since that's what they'll need to act on;
// the owner view translates the same fields into outcome sentences -
// "can I trust this for a decision" rather than "what is the score."
function governanceSentence(status: string | null | undefined): string {
  if (status === "CRITICAL") return "This data is not well governed right now - treat any numbers from it with caution until issues are resolved.";
  if (status === "REVIEW_REQUIRED") return "This data is mostly governed but has open items worth checking before relying on it for a big decision.";
  if (status === "HEALTHY") return "This data is well-governed and safe to rely on for decisions.";
  return "Governance status hasn't been assessed yet.";
}

function qualitySentence(score: number | undefined): string {
  const value = score ?? 0;
  if (value >= 85) return `Data quality is strong (${value}/100) - trustworthy for reporting.`;
  if (value >= 60) return `Data quality is fair (${value}/100) - usable, but worth spot-checking for a high-stakes report.`;
  return `Data quality is weak (${value}/100) - verify before using this in anything customer-facing or financial.`;
}

function privacySentence(dataset: EcosystemDatasetNode): string {
  const piiCount = dataset.pii_columns ?? 0;
  if (piiCount === 0) return "No personal data detected here.";
  const consent = dataset.consent_status === "CONSENT_OBTAINED"
    ? "consent has been documented"
    : dataset.consent_status === "CONSENT_NOT_REQUIRED"
    ? "consent isn't required for this use"
    : "consent hasn't been reviewed yet";
  const retention = dataset.retention_status === "OVERDUE"
    ? "and it's past its retention window"
    : dataset.retention_status === "WITHIN_POLICY"
    ? "and it's within its retention policy"
    : "and no retention policy has been set";
  return `Contains ${piiCount} personal-data column${piiCount === 1 ? "" : "s"} - ${consent}, ${retention}.`;
}

function contractSentence(status: string | null | undefined): string {
  if (status === "COMPLIANT") return "A data contract protects this - upstream schema changes get caught before they break anything downstream.";
  if (status === "BREACHED") return "The data contract on this is currently breached - something upstream changed in a way consumers weren't expecting.";
  if (status === "PENDING_EVALUATION") return "A data contract exists but hasn't been evaluated yet.";
  return "No data contract in place - schema changes upstream could silently break reports built on this.";
}

function EcosystemLineageList({
  title,
  datasets,
  onSelectDataset,
}: {
  title: string;
  datasets: EcosystemDatasetNode[];
  onSelectDataset: (dataset: EcosystemDatasetNode) => void;
}) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</div>
      {datasets.length === 0 && <div className="text-sm text-gray-400">None.</div>}
      <div className="space-y-1">
        {datasets.map((dataset) => (
          <button
            key={dataset.id}
            type="button"
            onClick={() => onSelectDataset(dataset)}
            className="block w-full rounded border px-2 py-1.5 text-left text-sm hover:bg-gray-50"
          >
            {dataset.schema_name}.{dataset.name}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function EcosystemNodePanel({ graph, selection, audience, onClose, onSelectDataset }: Props) {
  if (!selection) {
    return (
      <div className="rounded-xl border bg-white p-6 text-sm text-gray-500">
        Click a node in the map to see what it contains: datasets, columns, PII, data quality, classification, policies, and lineage - one hop at a time.
      </div>
    );
  }

  const datasetById = new Map(graph.datasets.map((d) => [d.id, d]));

  if (selection.kind === "source") {
    const source = selection.source;
    const datasets = graph.datasets.filter((d) => d.source_id === source.id);

    return (
      <div className="rounded-xl border bg-white p-5">
        <div className="mb-3 flex items-start justify-between">
          <div>
            <div className="text-lg font-semibold">{source.name}</div>
            <div className="text-xs uppercase tracking-wide text-gray-500">{source.type} &middot; {source.tier.replace("_", " ")}</div>
          </div>
          <button onClick={onClose} className="text-sm text-gray-400 hover:text-gray-700">Close</button>
        </div>

        {audience === "analyst" ? (
          <div className="mb-4">
            <Row label="Datasets" value={source.dataset_count} />
            <Row label="Total columns" value={source.total_columns} />
            <Row label="PII columns" value={source.pii_columns} />
            <Row label="Worst governance status" value={source.worst_governance_status ?? "N/A"} />
          </div>
        ) : (
          <div className="mb-4 space-y-2">
            <Sentence>
              This system holds {source.dataset_count} table{source.dataset_count === 1 ? "" : "s"} ({source.total_columns} columns total).
            </Sentence>
            <Sentence>
              {source.pii_columns > 0
                ? `${source.pii_columns} of those columns contain personal data - handle per your privacy policy.`
                : "None of those columns contain personal data."}
            </Sentence>
            <Sentence>{governanceSentence(source.worst_governance_status)}</Sentence>
          </div>
        )}

        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">Datasets in this system</div>
          <div className="space-y-1">
            {datasets.map((dataset) => (
              <button
                key={dataset.id}
                type="button"
                onClick={() => onSelectDataset(dataset)}
                className="block w-full rounded border px-2 py-1.5 text-left text-sm hover:bg-gray-50"
              >
                {dataset.schema_name}.{dataset.name}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const dataset = selection.dataset;

  const upstream = graph.edges
    .filter((edge) => edge.downstream_dataset_id === dataset.id)
    .map((edge) => datasetById.get(edge.upstream_dataset_id))
    .filter((d): d is EcosystemDatasetNode => Boolean(d));

  const downstream = graph.edges
    .filter((edge) => edge.upstream_dataset_id === dataset.id)
    .map((edge) => datasetById.get(edge.downstream_dataset_id))
    .filter((d): d is EcosystemDatasetNode => Boolean(d));

  return (
    <div className="rounded-xl border bg-white p-5">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <div className="text-lg font-semibold">{dataset.schema_name}.{dataset.name}</div>
          <div className="text-xs uppercase tracking-wide text-gray-500">
            {dataset.tier.replace("_", " ")} {dataset.domain ? `· ${dataset.domain}` : ""}
          </div>
        </div>
        <button onClick={onClose} className="text-sm text-gray-400 hover:text-gray-700">Close</button>
      </div>

      {audience === "analyst" ? (
        <div className="mb-4">
          <Row label="Owner / steward" value={`${dataset.owner || "Unowned"} / ${dataset.steward || "–"}`} />
          <Row label="System role" value={dataset.system_role ?? "–"} />
          <Row label="Data category" value={dataset.data_category ?? "–"} />
          <Row label="Classification / sensitivity" value={dataset.sensitivity_score ?? "LOW"} />
          <Row label="Total / PII columns" value={`${dataset.total_columns ?? 0} / ${dataset.pii_columns ?? 0}`} />
          <Row label="Governance status" value={dataset.governance_status ?? "UNKNOWN"} />
          <Row label="Governance score" value={dataset.governance_score ?? 0} />
          <Row label="Quality score" value={dataset.quality_score ?? 0} />
          <Row label="Freshness" value={dataset.freshness_status ?? "UNKNOWN"} />
          <Row label="Contract status" value={dataset.contract_status ?? "NO_CONTRACT"} />
          <Row label="Purpose" value={dataset.purpose || "–"} />
          <Row label="Consent status" value={dataset.consent_status ?? "NOT_ASSESSED"} />
          <Row label="Retention status" value={dataset.retention_status ?? "NOT_SET"} />
          <Row label="Privacy score" value={dataset.privacy_score ?? 0} />
        </div>
      ) : (
        <div className="mb-4 space-y-2">
          <Sentence>{governanceSentence(dataset.governance_status)}</Sentence>
          <Sentence>{qualitySentence(dataset.quality_score)}</Sentence>
          <Sentence>{privacySentence(dataset)}</Sentence>
          <Sentence>{contractSentence(dataset.contract_status)}</Sentence>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 border-t pt-3">
        <EcosystemLineageList title="Comes from (upstream)" datasets={upstream} onSelectDataset={onSelectDataset} />
        <EcosystemLineageList title="Feeds into (downstream)" datasets={downstream} onSelectDataset={onSelectDataset} />
      </div>

      <Link
        href={`/datasets/${dataset.id}`}
        className="mt-4 block rounded-lg border px-3 py-2 text-center text-sm text-gray-700 hover:bg-gray-50"
      >
        Open full dataset page &rarr;
      </Link>
    </div>
  );
}
