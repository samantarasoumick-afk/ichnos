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
  EcosystemGlossaryTermNode,
  EcosystemGraph as EcosystemGraphData,
  EcosystemProcessNode,
  EcosystemSourceNode,
  EcosystemTier,
} from "../types/metadata";

export type EcosystemSelection =
  | { kind: "source"; source: EcosystemSourceNode }
  | { kind: "dataset"; dataset: EcosystemDatasetNode }
  | { kind: "process"; process: EcosystemProcessNode }
  | { kind: "glossary_term"; term: EcosystemGlossaryTermNode };

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

// The governance layer (processes, glossary terms) cuts across the
// front/middle/back-office tiers rather than living in one of them, so
// it gets its own two columns to the right of the tier columns, styled
// distinctly from TIER_STYLE so it reads as "a different kind of
// node" rather than a sixth tier.
const PROCESS_STYLE = { background: "#eef2ff", border: "#6366f1", label: "Business processes" };
const GLOSSARY_STYLE = { background: "#ecfeff", border: "#06b6d4", label: "Glossary terms" };

const CONTRACT_BADGE: Record<string, { label: string; color: string }> = {
  COMPLIANT: { label: "Contract OK", color: "#22c55e" },
  BREACHED: { label: "Contract breached", color: "#ef4444" },
  PENDING_EVALUATION: { label: "Contract pending", color: "#f59e0b" },
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
  selected: boolean,
  contractStatus: string | null | undefined
): Node {
  const style = TIER_STYLE[dataset.tier];
  const dot = dataset.governance_status ? GOVERNANCE_DOT[dataset.governance_status] : undefined;
  const contractBadge = contractStatus ? CONTRACT_BADGE[contractStatus] : undefined;

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
          {contractBadge && (
            <div
              className="mt-1 inline-block rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase"
              style={{ background: `${contractBadge.color}1a`, color: contractBadge.color }}
            >
              {contractBadge.label}
            </div>
          )}
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

function processNode(process: EcosystemProcessNode, position: { x: number; y: number }, selected: boolean): Node {
  return {
    id: process.id,
    position,
    data: {
      label: (
        <div>
          <div className="font-semibold">{process.name}</div>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-gray-500">Business process</div>
          <div className="mt-1 text-xs text-gray-600">
            {process.dataset_ids.length} dataset{process.dataset_ids.length === 1 ? "" : "s"} touched
            {process.owner ? ` · ${process.owner}` : ""}
          </div>
        </div>
      ),
    },
    style: {
      border: `1.5px solid ${PROCESS_STYLE.border}`,
      background: selected ? PROCESS_STYLE.border : PROCESS_STYLE.background,
      color: selected ? "#fff" : undefined,
      borderRadius: 8,
      padding: 10,
      width: 236,
      fontSize: 12,
      cursor: "pointer",
    },
  };
}

function glossaryTermNode(
  term: EcosystemGlossaryTermNode,
  position: { x: number; y: number },
  selected: boolean
): Node {
  return {
    id: term.id,
    position,
    data: {
      label: (
        <div>
          <div className="font-semibold">{term.term}</div>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-gray-500">
            Glossary term{term.domain ? ` · ${term.domain}` : ""}
          </div>
          <div className="mt-1 text-xs text-gray-600">
            {term.dataset_ids.length} dataset{term.dataset_ids.length === 1 ? "" : "s"} tagged
          </div>
        </div>
      ),
    },
    style: {
      border: `1.5px solid ${GLOSSARY_STYLE.border}`,
      background: selected ? GLOSSARY_STYLE.border : GLOSSARY_STYLE.background,
      color: selected ? "#fff" : undefined,
      borderRadius: 8,
      padding: 10,
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

  const datasetById = new Map(graph.datasets.map((d) => [d.id, d]));
  const processById = new Map(graph.processes.map((p) => [p.id, p]));
  const termById = new Map(graph.glossary_terms.map((t) => [t.id, t]));
  const contractByDatasetId = new Map(graph.contracts.map((c) => [c.dataset_id, c]));

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
          const contract = contractByDatasetId.get(dataset.id);
          nodes.push(
            datasetChildNode(dataset, { x: x + 30, y: yCursor }, selectedId === dataset.id, contract?.last_status)
          );
          yCursor += DATASET_ROW_HEIGHT;
        });
      }

      yCursor += ROW_GAP;
    });
  });

  // The governance layer (processes, glossary terms) doesn't belong to
  // any one tier, so it gets its own two columns past the tier columns
  // rather than being squeezed into one of them.
  const PROCESS_COLUMN = COLUMN_ORDER.length;
  const GLOSSARY_COLUMN = COLUMN_ORDER.length + 1;

  graph.processes.forEach((process, index) => {
    const y = index * (HEADER_HEIGHT + ROW_GAP);
    nodes.push(processNode(process, { x: PROCESS_COLUMN * COLUMN_WIDTH, y }, selectedId === process.id));
  });

  graph.glossary_terms.forEach((term, index) => {
    const y = index * (HEADER_HEIGHT + ROW_GAP);
    nodes.push(glossaryTermNode(term, { x: GLOSSARY_COLUMN * COLUMN_WIDTH, y }, selectedId === term.id));
  });

  // A dataset resolves to its own node id if its source is expanded,
  // otherwise it collapses to its parent source's node id - this is
  // what makes edges re-target automatically on expand/collapse.
  function nodeIdForDataset(datasetId: string, sourceId: string): string {
    return expanded.has(sourceId) ? datasetId : sourceId;
  }

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

  // Governance-layer edges (process/glossary -> dataset) reuse the
  // same collapse-aware target resolution as lineage edges, but get a
  // visually distinct (dashed, unanimated) style so they read as "this
  // node touches that dataset" rather than "data flows this way".
  const governanceEdgeIds = new Set<string>();

  graph.process_edges.forEach((edge) => {
    const dataset = datasetById.get(edge.dataset_id);
    if (!dataset) return;
    const target = nodeIdForDataset(dataset.id, dataset.source_id);
    const key = `${edge.process_id}->${target}`;
    if (governanceEdgeIds.has(key)) return;
    governanceEdgeIds.add(key);
    edges.push({
      id: `process-${key}`,
      source: edge.process_id,
      target,
      label: "process",
      style: { stroke: PROCESS_STYLE.border, strokeDasharray: "4 3" },
      labelStyle: { fill: PROCESS_STYLE.border, fontSize: 10 },
    });
  });

  graph.glossary_edges.forEach((edge) => {
    const dataset = datasetById.get(edge.dataset_id);
    if (!dataset) return;
    const target = nodeIdForDataset(dataset.id, dataset.source_id);
    const key = `${edge.term_id}->${target}`;
    if (governanceEdgeIds.has(key)) return;
    governanceEdgeIds.add(key);
    edges.push({
      id: `term-${key}`,
      source: edge.term_id,
      target,
      label: "term",
      style: { stroke: GLOSSARY_STYLE.border, strokeDasharray: "4 3" },
      labelStyle: { fill: GLOSSARY_STYLE.border, fontSize: 10 },
    });
  });

  function handleNodeClick(_event: React.MouseEvent, node: Node) {
    const dataset = datasetById.get(node.id);
    if (dataset) {
      onSelect({ kind: "dataset", dataset });
      return;
    }
    const source = graph.sources.find((s) => s.id === node.id);
    if (source) {
      onSelect({ kind: "source", source });
      return;
    }
    const process = processById.get(node.id);
    if (process) {
      onSelect({ kind: "process", process });
      return;
    }
    const term = termById.get(node.id);
    if (term) onSelect({ kind: "glossary_term", term });
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
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-3 w-3 rounded-sm"
            style={{ background: PROCESS_STYLE.background, border: `1px solid ${PROCESS_STYLE.border}` }}
          />
          {PROCESS_STYLE.label}
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-3 w-3 rounded-sm"
            style={{ background: GLOSSARY_STYLE.background, border: `1px solid ${GLOSSARY_STYLE.border}` }}
          />
          {GLOSSARY_STYLE.label}
        </span>
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
