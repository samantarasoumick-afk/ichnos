"use client";

import { useRouter } from "next/navigation";

import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  type Edge,
  type Node,
} from "reactflow";

import type {
  Dataset,
  Lineage,
} from "../types/metadata";

type Props = {
  datasets: Dataset[];
  lineage: Lineage[];
};

function datasetLabel(dataset: Dataset) {
  return `${dataset.schema_name}.${dataset.name}`;
}

const SENSITIVITY_STYLE: Record<string, { background: string; border: string }> = {
  HIGH: { background: "#fef2f2", border: "#ef4444" },
  MEDIUM: { background: "#fffbeb", border: "#f59e0b" },
  LOW: { background: "#f0fdf4", border: "#22c55e" },
};

/**
 * Depth-based left-to-right layout: a dataset's depth is one more
 * than the deepest of its upstream dependencies, so root sources
 * (nothing feeds into them) sit on the left and the graph reads in
 * the same direction data actually flows. Falls back to depth 0 for
 * any node reachable only via a cycle (shouldn't happen in practice,
 * but avoids infinite recursion if it ever does).
 */
function computeDepths(nodeIds: string[], lineage: Lineage[]): Map<string, number> {
  const incomingBySource = new Map<string, string[]>();
  nodeIds.forEach((id) => incomingBySource.set(id, []));

  lineage.forEach((edge) => {
    const list = incomingBySource.get(edge.downstream_dataset_id);
    if (list) list.push(edge.upstream_dataset_id);
  });

  const depths = new Map<string, number>();
  const inProgress = new Set<string>();

  function depthOf(id: string): number {
    if (depths.has(id)) return depths.get(id)!;
    if (inProgress.has(id)) return 0;

    inProgress.add(id);
    const upstreamIds = incomingBySource.get(id) || [];
    const depth = upstreamIds.length === 0
      ? 0
      : Math.max(...upstreamIds.map((upstreamId) => depthOf(upstreamId) + 1));
    inProgress.delete(id);

    depths.set(id, depth);
    return depth;
  }

  nodeIds.forEach((id) => depthOf(id));
  return depths;
}

export default function LineageGraph({
  datasets,
  lineage,
}: Props) {
  const router = useRouter();

  const datasetById = new Map(
    datasets.map((dataset) => [
      dataset.id,
      dataset,
    ])
  );

  const relatedIds = new Set<string>();

  lineage.forEach((edge) => {
    relatedIds.add(edge.upstream_dataset_id);
    relatedIds.add(edge.downstream_dataset_id);
  });

  const graphDatasets = datasets.filter((dataset) =>
    relatedIds.has(dataset.id)
  );

  const depths = computeDepths(
    graphDatasets.map((dataset) => dataset.id),
    lineage
  );

  const countPerDepth = new Map<number, number>();

  const nodes: Node[] = graphDatasets.map((dataset) => {
    const depth = depths.get(dataset.id) ?? 0;
    const rowIndex = countPerDepth.get(depth) ?? 0;
    countPerDepth.set(depth, rowIndex + 1);

    const style = SENSITIVITY_STYLE[dataset.sensitivity_score || "LOW"] || SENSITIVITY_STYLE.LOW;

    return {
      id: dataset.id,
      position: {
        x: depth * 280,
        y: rowIndex * 150,
      },
      data: {
        label: (
          <div>
            <div className="font-semibold">
              {datasetLabel(dataset)}
            </div>
            <div className="text-xs text-gray-500">
              {dataset.owner || "Unowned"}
            </div>
            <div className="mt-1 text-[10px] uppercase tracking-wide text-gray-400">
              {dataset.sensitivity_score || "LOW"} sensitivity
            </div>
          </div>
        ),
      },
      style: {
        border: `1.5px solid ${style.border}`,
        background: style.background,
        borderRadius: 8,
        padding: 12,
        width: 220,
        cursor: "pointer",
      },
    };
  });

  const edges: Edge[] = lineage
    .filter(
      (edge) =>
        datasetById.has(edge.upstream_dataset_id) &&
        datasetById.has(edge.downstream_dataset_id)
    )
    .map((edge) => ({
      id: edge.id,
      source: edge.upstream_dataset_id,
      target: edge.downstream_dataset_id,
      label: edge.transformation_type || "lineage",
      animated: true,
      markerEnd: {
        type: MarkerType.ArrowClosed,
      },
    }));

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-gray-500">
        <span>Left to right = upstream to downstream. Click a node to open the dataset.</span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: "#f0fdf4", border: "1px solid #22c55e" }} />
          Low sensitivity
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: "#fffbeb", border: "1px solid #f59e0b" }} />
          Medium sensitivity
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: "#fef2f2", border: "1px solid #ef4444" }} />
          High sensitivity
        </span>
      </div>

      <div className="h-[640px] rounded-lg border bg-white">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={(_event, node) => router.push(`/datasets/${node.id}`)}
          fitView
        >
          <MiniMap />
          <Controls />
          <Background />
        </ReactFlow>
      </div>
    </div>
  );
}
