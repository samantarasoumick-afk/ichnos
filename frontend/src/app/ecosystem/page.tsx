"use client";

import { useEffect, useMemo, useState } from "react";

import EcosystemGraph, { type EcosystemSelection } from "../../components/EcosystemGraph";
import EcosystemNodePanel from "../../components/EcosystemNodePanel";
import OnboardingProgressWidget from "../../components/OnboardingProgressWidget";
import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type {
  EcosystemDatasetNode,
  EcosystemGraph as EcosystemGraphData,
  OnboardingMilestoneKey,
  OnboardingProgress,
  SearchResponse,
  SearchResultItem,
} from "../../types/metadata";

type Audience = "analyst" | "owner";

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

  const [graph, setGraph] = useState<EcosystemGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [audience, setAudience] = useState<Audience>("analyst");
  const [selection, setSelection] = useState<EcosystemSelection | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [searching, setSearching] = useState(false);

  const [progress, setProgress] = useState<OnboardingProgress | null>(null);

  // Fire-and-forget: recording an onboarding milestone should never
  // block or interrupt whatever the person is actually doing on the
  // map, and a failure here (network hiccup) isn't worth surfacing as
  // an error - it just tries again the next time the same action happens.
  async function recordMilestone(key: OnboardingMilestoneKey) {
    try {
      const response = await api.post<OnboardingProgress>(`/api/ecosystem/onboarding/milestones/${key}`);
      setProgress(response.data);
    } catch (error) {
      console.error(error);
    }
  }

  useEffect(() => {
    if (!user) return;

    async function fetchGraph() {
      try {
        setErrorMessage(null);
        const response = await api.get<EcosystemGraphData>("/api/ecosystem");
        setGraph(response.data);
        recordMilestone("VIEWED_ECOSYSTEM_MAP");
      } catch (error) {
        console.error(error);
        setErrorMessage("Unable to load the ecosystem map. Please make sure the backend is running.");
      } finally {
        setLoading(false);
      }
    }

    async function fetchProgress() {
      try {
        const response = await api.get<OnboardingProgress>("/api/ecosystem/onboarding/progress");
        setProgress(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    fetchGraph();
    fetchProgress();
  }, [user]);

  function toggleExpand(sourceId: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) next.delete(sourceId);
      else next.add(sourceId);
      return next;
    });
  }

  // Shared by the graph's own node clicks and every "jump to this
  // dataset" shortcut (search results, lineage-list rows in the
  // panel) - wherever a source/dataset gets selected, the milestone
  // for exploring that tier fires the same way.
  function applySelection(next: EcosystemSelection) {
    setSelection(next);
    const tier = next.kind === "source" ? next.source.tier : next.dataset.tier;
    if (tier === "FRONT_OFFICE") recordMilestone("EXPLORED_FRONT_OFFICE");
    else if (tier === "MIDDLE_OFFICE") recordMilestone("EXPLORED_MIDDLE_OFFICE");
    else if (tier === "BACK_OFFICE") recordMilestone("EXPLORED_BACK_OFFICE");
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

  const selectedId = selection
    ? selection.kind === "source"
      ? selection.source.id
      : selection.dataset.id
    : null;

  const stats = useMemo(() => {
    if (!graph) return null;
    return {
      sources: graph.sources.length,
      datasets: graph.datasets.length,
      hops: graph.edges.length,
      pii: graph.datasets.reduce((sum, d) => sum + (d.pii_columns ?? 0), 0),
    };
  }, [graph]);

  async function runSemanticSearch() {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setSearchResults([]);
      return;
    }

    setSearching(true);
    try {
      const response = await api.get<SearchResponse>("/api/search", { params: { q: trimmed, limit: 6 } });
      setSearchResults(response.data.results);
      recordMilestone("USED_SEMANTIC_SEARCH");
    } catch (error) {
      console.error(error);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  function openSearchResult(result: SearchResultItem) {
    if (result.type !== "dataset" || !graph) return;
    const dataset = graph.datasets.find((d) => d.id === result.id);
    if (dataset) selectDataset(dataset);
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-lg bg-white p-6 shadow">Loading...</div>
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

      {loading && <div className="rounded-lg bg-white p-6 shadow">Loading the ecosystem map...</div>}

      {!loading && !errorMessage && graph && (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-white p-4 shadow">
            <div className="flex flex-wrap gap-6 text-sm text-gray-600">
              <span><strong className="text-gray-900">{stats?.sources}</strong> connected systems</span>
              <span><strong className="text-gray-900">{stats?.datasets}</strong> datasets</span>
              <span><strong className="text-gray-900">{stats?.hops}</strong> lineage hops</span>
              <span><strong className="text-gray-900">{stats?.pii}</strong> PII columns tracked</span>
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

          <p className="mb-4 text-sm text-gray-500">{AUDIENCE_COPY[audience].blurb}</p>

          <div className="mb-6 rounded-xl bg-white p-4 shadow">
            <div className="mb-1 text-sm font-semibold text-gray-700">
              Ask the map anything &mdash; powered by vector/semantic search over the catalog
            </div>
            <p className="mb-3 text-xs text-gray-500">
              This searches by meaning, not just keyword match (real embeddings when Voyage AI is configured, a
              deterministic local fallback otherwise) - so &ldquo;where does churn risk get calculated&rdquo; can
              surface the right dataset even without the exact table name.
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
                    disabled={result.type !== "dataset"}
                    className="flex w-full items-center justify-between rounded border px-3 py-2 text-left text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
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

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <EcosystemGraph
                graph={graph}
                selectedId={selectedId}
                onSelect={applySelection}
                expanded={expanded}
                onToggleExpand={toggleExpand}
              />
            </div>
            <div className="space-y-6">
              <OnboardingProgressWidget progress={progress} />
              <EcosystemNodePanel
                graph={graph}
                selection={selection}
                audience={audience}
                onClose={() => setSelection(null)}
                onSelectDataset={selectDataset}
                onTrace={() => recordMilestone("TRACED_PROVENANCE")}
              />
            </div>
          </div>
        </>
      )}
    </main>
  );
}
