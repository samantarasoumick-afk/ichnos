"use client";

import { useMemo } from "react";

import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  type Edge,
  type Node,
} from "reactflow";

import type {
  EcosystemDatasetNode,
  EcosystemGraph as EcosystemGraphData,
  EcosystemSourceNode,
  EcosystemTier,
} from "../types/metadata";

export type EcosystemSelection =
  | { kind: "source"; source: EcosystemSourceNode }
  | { kind: "dataset"; dataset: EcosystemDatasetNode };

type Props = {
  graph: EcosystemGraphData;
  selectedId: string | null;
  onSelect: (selection: EcosystemSelection) => void;
  expanded: Set<string>;
  onToggleExpand: (sourceId: string) => void;
};

// Reads left-to-right the same direction data actually flows: front
// office (origination) on the left, back office (reporting) on the
// right. MIXED sources (genuinely span more than one tier) and
// STANDALONE ones (no lineage yet) get their own columns further
// right rather than being forced into a single arbitrary tier.
const COLUMN_ORDER: EcosystemTier[] = ["FRONT_OFFICE", "MIDDLE_OFFICE", "BACK_OFFICE", "MIXED", "STANDALONE"];

const COLUMN_WIDTH = 340;
const HEADER_HEIGHT = 118;
const DATASET_ROW_HEIGHT = 92;
const ROW_GAP = 24;

const TIER_STYLE: Record<EcosystemTier, { background: string; border: string; label: string }> = {
  FRONT_OFFICE: { background: "#eff6ff", border: "#3b82f6", label: "Front office" },
  MIDDLE_OFFICE: { background: "#faf5ff", border: "#a855f7", label: "Middle office" },
  BACK_OFFICE: { background: "#f0fdf4", border: "#22c55e", label: "Back office" },
  MIXED: { background: "#fffbeb", border: "#f59e0b", label: "Mixed" },
  STANDALONE: { background: "#f9fafb", border: "#9ca3af", label: "Not yet connected" },
};

const GOVERNANCE_DOT: Record<string, string> = {
  CRITICAL: "#ef4444",
  REVIEW_REQUIRED: "#f59e0b",
  HEALTHY: "#22c55e",
};

function sourceHeaderNode(
  source: EcosystemSourceNode,
  position: { x: number; y: number },
  expanded: boolean,
  selected: boolean,
  onToggleExpand: (event: React.MouseEvent) => void
): Node {
  const style = TIER_STYLE[source.tier];
  const dot = source.worst_governance_status ? GOVERNANCE_DOT[source.worst_governance_status] : undefined;

  return {
    id: source.id,
    position,
    data: {
      label: (
        <div>
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold">{source.name}</span>
            <button
              type="button"
              onClick={onToggleExpand}
              className="shrink-0 rounded border border-gray-300 bg-white px-1.5 text-[10px] text-gray-600 hover:bg-gray-50"
            >
              {expanded ? "−" : "+"}
            </button>
          </div>
          <div className="text-[10px] uppercase tracking-wide text-gray-500">{source.type}</div>
          <div className="mt-1 text-xs text-gray-600">
            {source.dataset_count} dataset{source.dataset_count === 1 ? "" : "s"} &middot; {source.total_columns} columns
          </div>
          <div className="mt-0.5 flex items-center gap-1 text-xs text-gray-600">
            {dot && <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} />}
            {source.pii_columns > 0 ? `${source.pii_columns} PII column${source.pii_columns === 1 ? "" : "s"}` : "No PII"}
          </div>
        </div>
      ),
    },
    style: {
      border: `2px solid ${style.border}`,
      background: selected ? style.border : style.background,
      color: selected ? "#fff" : undefined,
      borderRadius: 10,
      padding: 12,
      width: 260,
      cursor: "pointer",
    },
  };
}

function datasetChildNode(
  dataset: EcosystemDatasetNode,
  position: { x: number; y: number },
  selected: boolean
): Node {
  const style = TIER_STYLE[dataset.tier];
  const dot = dataset.governance_status ? GOVERNANCE_DOT[dataset.governance_status] : undefined;

  return {
    id: dataset.id,
    position,
    data: {
      label: (
        <div>
          <div className="font-medium">
            {dataset.schema_name}.{dataset.name}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-gray-500">
            {dot && <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} />}
            <span>{dataset.total_columns ?? 0} cols</span>
            <span>&middot;</span>
            <span>{dataset.pii_columns ?? 0} PII</span>
            <span>&middot;</span>
            <span>DQ {dataset.quality_score ?? 0}</span>
          </div>
        </div>
      ),
    },
    style: {
      border: `1.5px solid ${style.border}`,
      background: selected ? style.border : "#ffffff",
      color: selected ? "#fff" : undefined,
      borderRadius: 8,
      padding: 8,
      width: 236,
      fontSize: 12,
      cursor: "pointer",
    },
  };
}

/**
 * The drill-down: a source starts collapsed (one rolled-up node).
 * Expanding it swaps that single node for its individual dataset
 * nodes, and every lineage edge touching those datasets re-targets
 * itself live - so an edge that pointed at a collapsed source now
 * points at the exact dataset it's actually connected to. That's the
 * "incrementally shown, hop by hop" behavior: expand more sources and
 * the map gets more granular, one hop at a time, in either direction.
 */
export default function EcosystemGraph({ graph, selectedId, onSelect, expanded, onToggleExpand }: Props) {
  const datasetsBySource = useMemo(() => {
    const map = new Map<string, EcosystemDatasetNode[]>();
    graph.datasets.forEach((dataset) => {
      const list = map.get(dataset.source_id) ?? [];
      list.push(dataset);
      map.set(dataset.source_id, list);
    });
    return map;
  }, [graph.datasets]);

  const sourcesByTier = useMemo(() => {
    const map = new Map<EcosystemTier, EcosystemSourceNode[]>();
    COLUMN_ORDER.forEach((tier) => map.set(tier, []));
    graph.sources.forEach((source) => {
      const list = map.get(source.tier) ?? [];
      list.push(source);
      map.set(source.tier, list);
    });
    return map;
  }, [graph.sources]);

  const nodes: Node[] = [];

  COLUMN_ORDER.forEach((tier, columnIndex) => {
    const sources = sourcesByTier.get(tier) ?? [];
    let yCursor = 0;

    sources.forEach((source) => {
      const x = columnIndex * COLUMN_WIDTH;
      const isExpanded = expanded.has(source.id);

      nodes.push(
        sourceHeaderNode(
          source,
          { x, y: yCursor },
          isExpanded,
          selectedId === source.id,
          (event) => {
            event.stopPropagation();
            onToggleExpand(source.id);
          }
        )
      );
      yCursor += HEADER_HEIGHT;

      if (isExpanded) {
        const datasets = datasetsBySource.get(source.id) ?? [];
        datasets.forEach((dataset) => {
          nodes.push(datasetChildNode(dataset, { x: x + 30, y: yCursor }, selectedId === dataset.id));
          yCursor += DATASET_ROW_HEIGHT;
        });
      }

      yCursor += ROW_GAP;
    });
  });

  // A dataset resolves to its own node id if its source is expanded,
  // otherwise it collapses to its parent source's node id - this is
  // what makes edges re-target automatically on expand/collapse.
  function nodeIdForDataset(datasetId: string, sourceId: string): string {
    return expanded.has(sourceId) ? datasetId : sourceId;
  }

  const datasetById = new Map(graph.datasets.map((d) => [d.id, d]));

  const edgeMap = new Map<string, { count: number; label: string }>();
  graph.edges.forEach((edge) => {
    const upstream = datasetById.get(edge.upstream_dataset_id);
    const downstream = datasetById.get(edge.downstream_dataset_id);
    if (!upstream || !downstream) return;

    const source = nodeIdForDataset(upstream.id, upstream.source_id);
    const target = nodeIdForDataset(downstream.id, downstream.source_id);
    if (source === target) return;

    const key = `${source}->${target}`;
    const existing = edgeMap.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      edgeMap.set(key, { count: 1, label: edge.transformation_type || "lineage" });
    }
  });

  const edges: Edge[] = Array.from(edgeMap.entries()).map(([key, info]) => {
    const [source, target] = key.split("->");
    return {
      id: key,
      source,
      target,
      label: info.count > 1 ? `${info.label} (+${info.count - 1} more)` : info.label,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
    };
  });

  function handleNodeClick(_event: React.MouseEvent, node: Node) {
    const dataset = datasetById.get(node.id);
    if (dataset) {
      onSelect({ kind: "dataset", dataset });
      return;
    }
    const source = graph.sources.find((s) => s.id === node.id);
    if (source) onSelect({ kind: "source", source });
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-gray-500">
        <span>Front office (origin) &rarr; middle office (processing) &rarr; back office (reporting). Click + to drill into a source&apos;s datasets.</span>
        {COLUMN_ORDER.map((tier) => (
          <span key={tier} className="flex items-center gap-1">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ background: TIER_STYLE[tier].background, border: `1px solid ${TIER_STYLE[tier].border}` }}
            />
            {TIER_STYLE[tier].label}
          </span>
        ))}
      </div>

      <div className="h-[640px] rounded-lg border bg-white">
        <ReactFlow nodes={nodes} edges={edges} onNodeClick={handleNodeClick} fitView>
          <MiniMap />
          <Controls />
          <Background />
        </ReactFlow>
      </div>
    </div>
  );
}
