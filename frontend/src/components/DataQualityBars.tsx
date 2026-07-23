"use client";

import type { DataQuality, Dataset, EffectiveQuality } from "../types/metadata";

type Props = {
  dataQuality: DataQuality | null;
  effectiveQuality?: EffectiveQuality | null;
  allDatasets?: Dataset[];
};

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

function datasetLabel(dataset: Dataset | undefined, fallbackId: string) {
  if (!dataset) return fallbackId.slice(0, 8);
  return `${dataset.schema_name}.${dataset.name}`;
}

function EffectiveQualitySection({ effectiveQuality, allDatasets }: Pick<Props, "effectiveQuality" | "allDatasets">) {
  if (!effectiveQuality || effectiveQuality.contributing_edges.length === 0) return null;
  if (effectiveQuality.effective_score == null) return null;

  const effective = Math.round(effectiveQuality.effective_score);
  const own = effectiveQuality.own_score != null ? Math.round(effectiveQuality.own_score) : null;
  const delta = own != null ? effective - own : null;

  return (
    <div className="mt-5 pt-4 border-t">
      <div className="flex items-baseline gap-2">
        <div className="text-2xl font-bold">{effective}</div>
        <div className="text-sm text-gray-500">/ 100 lineage-adjusted</div>
        {delta !== null && delta !== 0 && (
          <span className={`text-xs font-medium ${delta > 0 ? "text-green-600" : "text-red-600"}`}>
            {delta > 0 ? "+" : ""}
            {delta} vs. own score
          </span>
        )}
      </div>
      <p className="text-xs text-gray-500 mt-1">
        {own === null
          ? "No standalone profile - this score is inherited from upstream lineage."
          : "Own profile blended with what's inherited from upstream lineage."}
      </p>

      <div className="mt-3 space-y-1.5">
        {effectiveQuality.contributing_edges.map((edge) => {
          const upstream = allDatasets?.find((d) => d.id === edge.upstream_dataset_id);
          return (
            <div key={edge.edge_id} className="text-xs text-gray-600 flex items-center justify-between gap-2">
              <span className="truncate">
                {datasetLabel(upstream, edge.upstream_dataset_id)} ({edge.upstream_effective_score})
              </span>
              <span className={`shrink-0 font-medium ${edge.adjustment > 0 ? "text-green-600" : edge.adjustment < 0 ? "text-red-600" : "text-gray-400"}`}>
                {edge.adjustment > 0 ? "+" : ""}
                {edge.adjustment} ({edge.documentation_completeness}% documented)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function DataQualityBars({ dataQuality, effectiveQuality, allDatasets }: Props) {
  if (!dataQuality) {
    if (effectiveQuality?.effective_score != null && effectiveQuality.contributing_edges.length > 0) {
      return (
        <div>
          <div className="text-sm text-gray-500">No standalone data quality profile yet.</div>
          <EffectiveQualitySection effectiveQuality={effectiveQuality} allDatasets={allDatasets} />
        </div>
      );
    }
    return <div className="text-sm text-gray-500">No data quality profile yet.</div>;
  }

  const overall = Math.round(dataQuality.overall_score ?? 0);

  return (
    <div>
      <div className="flex items-baseline gap-2">
        <div className="text-3xl font-bold">{overall}</div>
        <div className="text-sm text-gray-500">/ 100 overall</div>
      </div>

      <div className="mt-4 space-y-2.5">
        {DIMENSIONS.map(({ key, label }) => {
          const raw = dataQuality[key];
          const value = Math.round(typeof raw === "number" ? raw : 0);
          return (
            <div key={key}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-gray-500">{label}</span>
                <span className="font-medium text-gray-700">{value}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                <div
                  className={`h-full rounded-full ${barColor(value)}`}
                  style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <EffectiveQualitySection effectiveQuality={effectiveQuality} allDatasets={allDatasets} />
    </div>
  );
}
