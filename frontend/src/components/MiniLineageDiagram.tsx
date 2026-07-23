"use client";

import { useRouter } from "next/navigation";

import ReactFlow, {
  MarkerType,
  type Edge,
  type Node,
} from "reactflow";

import type { Dataset, Lineage } from "../types/metadata";

type Props = {
  dataset: Dataset;
  dependencies: Lineage[];
  impact: Lineage[];
  allDatasets: Dataset[];
};

const MAX_PER_SIDE = 4;

function datasetLabel(dataset: Dataset) {
  return `${dataset.schema_name}.${dataset.name}`;
}

const ROW_HEIGHT = 64;
const CENTER_X = 260;
const SIDE_X = 40;
const DOWNSTREAM_X = 480;

export default function MiniLineageDiagram({
  dataset,
  dependencies,
  impact,
  allDatasets,
}: Props) {
  const router = useRouter();

  const upstreamIds = Array.from(
    new Set(dependencies.map((edge) => edge.upstream_dataset_id))
  );
  const downstreamIds = Array.from(
    new Set(impact.map((edge) => edge.downstream_dataset_id))
  );

  const shownUpstream = upstreamIds.slice(0, MAX_PER_SIDE);
  const shownDownstream = downstreamIds.slice(0, MAX_PER_SIDE);
  const hiddenUpstreamCount = upstreamIds.length - shownUpstream.length;
  const hiddenDownstreamCount = downstreamIds.length - shownDownstream.length;

  const rowCount = Math.max(shownUpstream.length, shownDownstream.length, 1);
  const centerY = ((rowCount - 1) * ROW_HEIGHT) / 2;

  const nodes: Node[] = [
    {
      id: dataset.id,
      position: { x: CENTER_X, y: centerY },
      data: { label: <div className="font-semibold">{datasetLabel(dataset)}</div> },
      style: {
        border: "1.5px solid #111827",
        background: "#f3f4f6",
        borderRadius: 8,
        padding: 10,
        width: 180,
        fontSize: 12,
      },
    },
    ...shownUpstream.map((id, index) => {
      const upstream = allDatasets.find((d) => d.id === id);
      return {
        id,
        position: { x: SIDE_X, y: index * ROW_HEIGHT },
        data: { label: upstream ? datasetLabel(upstream) : "unknown" },
        style: {
          border: "1px solid #d1d5db",
          background: "#ffffff",
          borderRadius: 8,
          padding: 8,
          width: 160,
          fontSize: 11,
          cursor: "pointer",
        },
      };
    }),
    ...shownDownstream.map((id, index) => {
      const downstream = allDatasets.find((d) => d.id === id);
      return {
        id,
        position: { x: DOWNSTREAM_X, y: index * ROW_HEIGHT },
        data: { label: downstream ? datasetLabel(downstream) : "unknown" },
        style: {
          border: "1px solid #d1d5db",
          background: "#ffffff",
          borderRadius: 8,
          padding: 8,
          width: 160,
          fontSize: 11,
          cursor: "pointer",
        },
      };
    }),
  ];

  const edges: Edge[] = [
    ...shownUpstream.map((id) => ({
      id: `up-${id}`,
      source: id,
      target: dataset.id,
      markerEnd: { type: MarkerType.ArrowClosed },
    })),
    ...shownDownstream.map((id) => ({
      id: `down-${id}`,
      source: dataset.id,
      target: id,
      markerEnd: { type: MarkerType.ArrowClosed },
    })),
  ];

  if (upstreamIds.length === 0 && downstreamIds.length === 0) {
    return <div className="text-sm text-gray-500">No lineage recorded for this dataset.</div>;
  }

  return (
    <div>
      <div
        className="rounded-lg border bg-gray-50"
        style={{ height: Math.max(160, rowCount * ROW_HEIGHT + 40) }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={(_event, node) => {
            if (node.id !== dataset.id) router.push(`/datasets/${node.id}`);
          }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          proOptions={{ hideAttribution: true }}
          fitView
          fitViewOptions={{ padding: 0.2 }}
        />
      </div>

      {(hiddenUpstreamCount > 0 || hiddenDownstreamCount > 0) && (
        <div className="mt-2 text-xs text-gray-500">
          {hiddenUpstreamCount > 0 && `+${hiddenUpstreamCount} more upstream`}
          {hiddenUpstreamCount > 0 && hiddenDownstreamCount > 0 && " · "}
          {hiddenDownstreamCount > 0 && `+${hiddenDownstreamCount} more downstream`}
        </div>
      )}
    </div>
  );
}
