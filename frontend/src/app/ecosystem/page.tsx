"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import EcosystemGraph, { type EcosystemSelection } from "../../components/EcosystemGraph";
import EcosystemNodePanel from "../../components/EcosystemNodePanel";
import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type {
  EcosystemDatasetNode,
  EcosystemGraph as EcosystemGraphData,
  EcosystemSourceNode,
  SearchResponse,
  SearchResultItem,
} from "../../types/metadata";

type Audience = "analyst" | "owner";

// One entry per clickable stat chip in the summary bar. Each maps to a
// drill-down list built from data already sitting in `graph` - no new
// API calls needed, just a client-side filter/projection.
type StatFilterKind =
  | "sources"
  | "datasets"
  | "hops"
  | "pii"
  | "processes"
  | "glossaryTerms"
  | "breachedContracts";

const STAT_FILTER_TITLES: Record<StatFilterKind, string> = {
  sources: "Connected systems",
  datasets: "Datasets",
  hops: "Lineage hops",
  pii: "Datasets with PII columns",
  processes: "Business processes",
  glossaryTerms: "Glossary terms",
  breachedContracts: "Breached contracts",
};

type StatListItem = {
  key: string;
  label: string;
  sublabel: string;
  onClick: () => void;
};

const AUDIENCE_COPY: Record<Audience, { label: string; blurb: string }> = {
  analyst: {
    label: "Analyst view",
    blurb: "Technical detail - schemas, scores, statuses - the vocabulary you'll actually query and file tickets against.",
  },
  owner: {
    label: "Business owner view",
    blurb: "Same map, framed as outcomes: can I trust this, is it protected, what happens if it breaks.",
  },
};

export default function EcosystemPage() {
  const { user, loading: authLoading } = useRequireAuth();
  const router = useRouter();

  const [graph, setGraph] = useState<EcosystemGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [audience, setAudience] = useState<Audience>("analyst");
  const [selection, setSelection] = useState<EcosystemSelection | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [statFilter, setStatFilter] = useState<StatFilterKind | null>(null);
  const [mapExpanded, setMapExpanded] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (!user) return;

    async function fetchGraph() {
      try {
        setErrorMessage(null);
        const response = await api.get<EcosystemGraphData>("/api/ecosystem");
        setGraph(response.data);
      } catch (error) {
        console.error(error);
        setErrorMessage("Unable to load the ecosystem map. Please make sure the backend is running.");
      } finally {
        setLoading(false);
      }
    }

    fetchGraph();
  }, [user]);

  function toggleExpand(sourceId: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) next.delete(sourceId);
      else next.add(sourceId);
      return next;
    });
  }

  function applySelection(next: EcosystemSelection) {
    setSelection(next);
  }

  function selectDataset(dataset: EcosystemDatasetNode) {
    // Bringing a dataset into view means expanding its source so the
    // node the panel is describing actually exists on the map - this
    // is what lets a semantic search hit ("find me the churn model")
    // land the analyst on the right hop instead of just a fact panel
    // floating disconnected from the graph.
    setExpanded((prev) => new Set(prev).add(dataset.source_id));
    applySelection({ kind: "dataset", dataset });
  }

  function selectSource(source: EcosystemSourceNode) {
    setExpanded((prev) => new Set(prev).add(source.id));
    applySelection({ kind: "source", source });
  }

  // Deep-linkable from a "source" search result (GlobalSearch or this
  // page's own search box both link here as /ecosystem?sourceId=...) -
  // same one-time-effect-after-load pattern used elsewhere (e.g. the
  // Ask page's ?q= deep link), guarded so it only ever fires once per
  // page load rather than re-firing on every graph refetch.
  const ranSourceDeepLinkRef = useRef(false);
  useEffect(() => {
    if (!graph || ranSourceDeepLinkRef.current) return;
    ranSourceDeepLinkRef.current = true;

    const sourceId = new URLSearchParams(window.location.search).get("sourceId");
    if (!sourceId) return;

    const source = graph.sources.find((s) => s.id === sourceId);
    if (!source) return;

    // Deferred a tick rather than called synchronously in the effect
    // body (same reasoning as the Ask page's own ?q= deep link) -
    // this is a one-time reaction to the URL once the graph has
    // loaded, not state React should own the timing of. Inlined
    // rather than calling selectSource() directly so this effect
    // doesn't need that function in its dependency array.
    queueMicrotask(() => {
      setExpanded((prev) => new Set(prev).add(source.id));
      applySelection({ kind: "source", source });
    });
  }, [graph]);

  const selectedId = selection
    ? selection.kind === "source"
      ? selection.source.id
      : selection.kind === "dataset"
      ? selection.dataset.id
      : selection.kind === "process"
      ? selection.process.id
      : selection.term.id
    : null;

  const stats = useMemo(() => {
    if (!graph) return null;
    return {
      sources: graph.sources.length,
      datasets: graph.datasets.length,
      hops: graph.edges.length,
      pii: graph.datasets.reduce((sum, d) => sum + (d.pii_columns ?? 0), 0),
      processes: graph.processes.length,
      glossaryTerms: graph.glossary_terms.length,
      breachedContracts: graph.contracts.filter((c) => c.last_status === "BREACHED").length,
    };
  }, [graph]);

  // The list backing whichever stat chip is currently drilled into. Built
  // straight from the already-loaded graph - clicking "8 sources" doesn't
  // fetch anything, it just projects graph.sources into a clickable list
  // that reuses the exact same select* functions the map itself uses, so
  // picking an item here lands on the identical detail panel a map click
  // would produce.
  const statListItems: StatListItem[] = useMemo(() => {
    if (!graph || !statFilter) return [];

    const datasetById = new Map(graph.datasets.map((d) => [d.id, d]));
    const datasetLabel = (d: EcosystemDatasetNode) => `${d.schema_name}.${d.name}`;

    switch (statFilter) {
      case "sources":
        return graph.sources.map((source) => ({
          key: source.id,
          label: source.name,
          sublabel: `${source.type} · ${source.dataset_count} dataset${source.dataset_count === 1 ? "" : "s"} · ${source.pii_columns} PII col${source.pii_columns === 1 ? "" : "s"}`,
          onClick: () => selectSource(source),
        }));

      case "datasets":
        return graph.datasets.map((dataset) => ({
          key: dataset.id,
          label: datasetLabel(dataset),
          sublabel: `${dataset.total_columns ?? 0} cols · ${dataset.pii_columns ?? 0} PII · DQ ${dataset.quality_score ?? 0}`,
          onClick: () => selectDataset(dataset),
        }));

      case "hops":
        return graph.edges.map((edge, index) => {
          const upstream = datasetById.get(edge.upstream_dataset_id);
          const downstream = datasetById.get(edge.downstream_dataset_id);
          return {
            key: `${edge.id}-${index}`,
            label: `${upstream ? datasetLabel(upstream) : "Unknown"} → ${downstream ? datasetLabel(downstream) : "Unknown"}`,
            sublabel: edge.transformation_type || "lineage",
            onClick: () => {
              if (upstream) setExpanded((prev) => new Set(prev).add(upstream.source_id));
              if (downstream) selectDataset(downstream);
              else if (upstream) selectDataset(upstream);
            },
          };
        });

      case "pii":
        return graph.datasets
          .filter((dataset) => (dataset.pii_columns ?? 0) > 0)
          .sort((a, b) => (b.pii_columns ?? 0) - (a.pii_columns ?? 0))
          .map((dataset) => ({
            key: dataset.id,
            label: datasetLabel(dataset),
            sublabel: `${dataset.pii_columns} PII column${dataset.pii_columns === 1 ? "" : "s"}`,
            onClick: () => selectDataset(dataset),
          }));

      case "processes":
        return graph.processes.map((process) => ({
          key: process.id,
          label: process.name,
          sublabel: `${process.dataset_ids.length} dataset${process.dataset_ids.length === 1 ? "" : "s"} touched${process.owner ? ` · ${process.owner}` : ""}`,
          onClick: () => applySelection({ kind: "process", process }),
        }));

      case "glossaryTerms":
        return graph.glossary_terms.map((term) => ({
          key: term.id,
          label: term.term,
          sublabel: `${term.dataset_ids.length} dataset${term.dataset_ids.length === 1 ? "" : "s"} tagged${term.domain ? ` · ${term.domain}` : ""}`,
          onClick: () => applySelection({ kind: "glossary_term", term }),
        }));

      case "breachedContracts":
        return graph.contracts
          .filter((contract) => contract.last_status === "BREACHED")
          .map((contract) => {
            const dataset = datasetById.get(contract.dataset_id);
            return {
              key: contract.id,
              label: dataset ? datasetLabel(dataset) : contract.dataset_id,
              sublabel: contract.last_breach_details || "Contract breached",
              onClick: () => dataset && selectDataset(dataset),
            };
          });

      default:
        return [];
    }
    // selectDataset/selectSource are stable per-render closures over setState
    // setters only - including them would just make this recompute on every
    // render for no behavioral difference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, statFilter]);

  function toggleStatFilter(kind: StatFilterKind) {
    setStatFilter((prev) => (prev === kind ? null : kind));
  }

  async function runSemanticSearch() {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setSearchResults([]);
      return;
    }

    setSearching(true);
    try {
      const response = await api.get<SearchResponse>("/api/search", { params: { q: trimmed, limit: 9 } });
      setSearchResults(response.data.results);
    } catch (error) {
      console.error(error);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  function openSearchResult(result: SearchResultItem) {
    // Source and dataset both drill in place - the ecosystem graph
    // already has everything needed to render either as a node panel
    // right here. Columns (and everything else - glossary/process/
    // risk/control/discussion) don't have their own representation on
    // this map, so those fall through to a real navigation via the
    // result's own url instead.
    if (result.type === "source" && graph) {
      const source = graph.sources.find((s) => s.id === result.id);
      if (source) {
        selectSource(source);
        return;
      }
    }

    if (result.type === "dataset" && graph) {
      const dataset = graph.datasets.find((d) => d.id === result.id);
      if (dataset) {
        selectDataset(dataset);
        return;
      }
    }

    router.push(result.url);
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-6">
        <h1 className="text-4xl font-bold">Ecosystem View</h1>
        <p className="mt-2 text-gray-600">
          The whole data estate as one map: front office (where data originates) through middle office (processing)
          to back office (reporting) - and back the other way, from a report to the raw table it came from. Built
          for new-analyst onboarding: the goal is to compress the &ldquo;how does this all fit together&rdquo;
          ramp-up from months to days.
        </p>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">{errorMessage}</div>
      )}

      {loading && <div className="rounded-xl bg-white p-6 shadow">Loading the ecosystem map...</div>}

      {!loading && !errorMessage && graph && (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-white p-4 shadow">
            <div className="flex flex-wrap gap-2 text-sm text-gray-600">
              {(
                [
                  { kind: "sources" as const, value: stats?.sources, suffix: "connected systems" },
                  { kind: "datasets" as const, value: stats?.datasets, suffix: "datasets" },
                  { kind: "hops" as const, value: stats?.hops, suffix: "lineage hops" },
                  { kind: "pii" as const, value: stats?.pii, suffix: "PII columns tracked" },
                  { kind: "processes" as const, value: stats?.processes, suffix: "business processes" },
                  { kind: "glossaryTerms" as const, value: stats?.glossaryTerms, suffix: "glossary terms" },
                  { kind: "breachedContracts" as const, value: stats?.breachedContracts, suffix: "breached contracts" },
                ]
              ).map(({ kind, value, suffix }) => (
                <button
                  key={kind}
                  type="button"
                  onClick={() => toggleStatFilter(kind)}
                  title={`Click to see the ${suffix} and drill down`}
                  className={`rounded-lg border px-2.5 py-1 transition-colors ${
                    statFilter === kind
                      ? "border-black bg-black text-white"
                      : "border-transparent hover:border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  <strong className={statFilter === kind ? "text-white" : "text-gray-900"}>{value}</strong> {suffix}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              {(Object.keys(AUDIENCE_COPY) as Audience[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setAudience(option)}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${
                    audience === option ? "border-black bg-black text-white" : "text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {AUDIENCE_COPY[option].label}
                </button>
              ))}
            </div>
          </div>

          {statFilter && (
            <div className="mb-4 rounded-xl bg-white p-4 shadow">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-700">
                  {STAT_FILTER_TITLES[statFilter]} <span className="font-normal text-gray-400">({statListItems.length})</span>
                </div>
                <button
                  type="button"
                  onClick={() => setStatFilter(null)}
                  className="rounded-lg border px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
                >
                  Back to overview
                </button>
              </div>
              {statListItems.length === 0 ? (
                <p className="text-sm text-gray-500">Nothing here yet.</p>
              ) : (
                <div className="grid max-h-72 grid-cols-1 gap-1.5 overflow-y-auto sm:grid-cols-2">
                  {statListItems.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      onClick={item.onClick}
                      className="rounded border px-3 py-2 text-left text-sm hover:bg-gray-50"
                    >
                      <div className="font-medium text-gray-800">{item.label}</div>
                      <div className="text-xs text-gray-500">{item.sublabel}</div>
                    </button>
                  ))}
                </div>
              )}
              <p className="mt-2 text-xs text-gray-400">
                Pick an item to drill into its detail panel below - click the stat again, or &ldquo;Back to overview&rdquo;, to drill back up.
              </p>
            </div>
          )}

          <p className="mb-4 text-sm text-gray-500">{AUDIENCE_COPY[audience].blurb}</p>

          <div className="mb-6 rounded-xl bg-white p-4 shadow">
            <div className="mb-1 text-sm font-semibold text-gray-700">
              Ask the map anything &mdash; powered by vector/semantic search over the catalog
            </div>
            <p className="mb-3 text-xs text-gray-500">
              This searches by meaning, not just keyword match (real embeddings when Voyage AI is configured, a
              deterministic local fallback otherwise) - so &ldquo;where does churn risk get calculated&rdquo; can
              surface the right dataset even without the exact table name. Matches a system name (e.g.
              &ldquo;Salesforce&rdquo;) too - click it to drill straight into its datasets, then further into
              columns from there.
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && runSemanticSearch()}
                placeholder="e.g. where does the customer 360 report get its data from?"
                className="w-full rounded-lg border px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={runSemanticSearch}
                disabled={searching}
                className="shrink-0 rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                {searching ? "Searching..." : "Search"}
              </button>
            </div>

            {searchResults.length > 0 && (
              <div className="mt-3 space-y-1">
                {searchResults.map((result) => (
                  <button
                    key={`${result.type}-${result.id}`}
                    type="button"
                    onClick={() => openSearchResult(result)}
                    className="flex w-full items-center justify-between rounded border px-3 py-2 text-left text-sm hover:bg-gray-50"
                  >
                    <span>
                      <span className="mr-2 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] uppercase text-gray-600">
                        {result.type.replace("_", " ")}
                      </span>
                      {result.label}
                    </span>
                    <span className="text-xs text-gray-400">score {result.score.toFixed(2)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {mapExpanded ? (
            <div className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-gray-100 p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-xl font-bold">Ecosystem map &mdash; expanded view</h2>
                <button
                  type="button"
                  onClick={() => setMapExpanded(false)}
                  className="rounded-lg border bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
                >
                  Exit expanded view ✕
                </button>
              </div>
              <div className="grid flex-1 grid-cols-1 gap-6 lg:grid-cols-4">
                <div className="lg:col-span-3">
                  <EcosystemGraph
                    graph={graph}
                    selectedId={selectedId}
                    onSelect={applySelection}
                    expanded={expanded}
                    onToggleExpand={toggleExpand}
                    heightClass="h-[calc(100vh-200px)]"
                  />
                </div>
                <div className="space-y-6 overflow-y-auto">
                  <EcosystemNodePanel
                    graph={graph}
                    selection={selection}
                    audience={audience}
                    onClose={() => setSelection(null)}
                    onSelectDataset={selectDataset}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <div className="mb-2 flex justify-end">
                  <button
                    type="button"
                    onClick={() => setMapExpanded(true)}
                    className="rounded-lg border bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
                  >
                    Expand map ⤢
                  </button>
                </div>
                <EcosystemGraph
                  graph={graph}
                  selectedId={selectedId}
                  onSelect={applySelection}
                  expanded={expanded}
                  onToggleExpand={toggleExpand}
                />
              </div>
              <div className="space-y-6">
                <EcosystemNodePanel
                  graph={graph}
                  selection={selection}
                  audience={audience}
                  onClose={() => setSelection(null)}
                  onSelectDataset={selectDataset}
                />
              </div>
            </div>
          )}
        </>
      )}
    </main>
  );
}
