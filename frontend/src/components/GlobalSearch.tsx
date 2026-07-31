"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import api from "../services/api";
import { useMentionPicker } from "../hooks/useMentionPicker";
import { fetchInlineAnswer, isQuestionLike } from "../utils/unifiedSearch";
import { ENTITY_TYPE_BADGE_CLASSES, ENTITY_TYPE_LABELS } from "./entityTypeStyles";
import MentionDropdown from "./MentionDropdown";
import SearchAnswerCard from "./SearchAnswerCard";
import type { AskResponse, MentionItem, SearchResponse, SearchResultItem, SearchResultType } from "../types/metadata";

const DEBOUNCE_MS = 250;

// The three tiers of the catalog hierarchy get their own labeled
// section, in drill-down order (system -> table -> field), so a
// search for a source name reads as "here's the source, and here's
// what's under it" rather than one flat, unordered list. Everything
// else (glossary/process/risk/control/discussion) still shows up,
// just grouped under one lighter-weight heading at the end.
const RESULT_GROUPS: { key: string; label: string; types: SearchResultType[] }[] = [
  { key: "source", label: "Sources", types: ["source"] },
  { key: "dataset", label: "Datasets", types: ["dataset"] },
  { key: "column", label: "Columns", types: ["column"] },
  {
    key: "other",
    label: "More",
    types: ["glossary_term", "process", "risk", "control", "discussion_thread"],
  },
];

export default function GlobalSearch() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);
  const mention = useMentionPicker();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  // The unified-search half: a synthesized answer shown above the
  // entity results whenever the typed text reads as a question (see
  // isQuestionLike), fetched in parallel with - not blocking - the
  // entity search above, since the two can resolve at different speeds
  // and neither should hold the other back.
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [asking, setAsking] = useState(false);

  // Close on click outside, same pattern as TopNav's NavDropdown.
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Cleanup only - the actual debounced fetch is triggered directly
  // from the input's onChange below, not from an effect reacting to
  // `query`. Calling setState synchronously inside an effect body
  // (rather than from an event handler or a callback) causes
  // cascading renders and trips the react-hooks/set-state-in-effect
  // rule; triggering the fetch from the change handler itself avoids
  // that while behaving identically.
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  function scheduleSearch(value: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = value.trim();

    if (!trimmed) {
      setResults([]);
      setLoading(false);
      setActiveIndex(-1);
      setAnswer(null);
      setAsking(false);
      return;
    }

    setLoading(true);

    const wantsAnswer = isQuestionLike(trimmed);
    setAsking(wantsAnswer);
    if (!wantsAnswer) setAnswer(null);

    debounceRef.current = setTimeout(() => {
      // Guards against an earlier, slower request's response landing
      // after a newer one and clobbering it with stale results. Shared
      // across both calls below so a stale answer can't land after a
      // newer entity-search response either, or vice versa.
      const requestId = ++requestIdRef.current;

      (async () => {
        try {
          const response = await api.get<SearchResponse>("/api/search", {
            params: { q: trimmed, limit: 15 },
          });

          if (requestId === requestIdRef.current) {
            setResults(response.data.results);
            setActiveIndex(-1);
          }
        } catch (error) {
          console.error(error);
          if (requestId === requestIdRef.current) {
            setResults([]);
          }
        } finally {
          if (requestId === requestIdRef.current) {
            setLoading(false);
          }
        }
      })();

      // Fired independently of the entity search above, not awaited
      // after it - a synthesized answer can take longer than a plain
      // ranking, and the entity list shouldn't sit blank waiting for it.
      if (wantsAnswer) {
        (async () => {
          const result = await fetchInlineAnswer(trimmed);
          if (requestId === requestIdRef.current) {
            setAnswer(result);
            setAsking(false);
          }
        })();
      }
    }, DEBOUNCE_MS);
  }

  function selectResult(result: SearchResultItem) {
    setOpen(false);
    setQuery("");
    setResults([]);
    setAnswer(null);
    setAsking(false);
    router.push(result.url);
  }

  // Passed to SearchAnswerCard so clicking a citation or "Continue in
  // Ask'Fe'" tidies up the dropdown the exact same way selecting an
  // entity result does, before navigating.
  function closeDropdown() {
    setOpen(false);
    setQuery("");
    setResults([]);
    setAnswer(null);
    setAsking(false);
  }

  function selectMention(item: MentionItem) {
    const el = inputRef.current;
    const caret = el?.selectionStart ?? query.length;
    const inserted = mention.buildInsertion(query, caret, item);

    mention.close();

    if (!inserted) return;

    setQuery(inserted.value);
    // Selecting a mention hands the search bar an exact entity name -
    // may as well run the normal search with it immediately, so the
    // dropdown transitions straight into that result (which will rank
    // first, being an exact label match) instead of sitting empty.
    scheduleSearch(inserted.value);

    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(inserted.caret, inserted.caret);
    });
  }

  // Grouped in drill-down order (source -> dataset -> column -> more)
  // rather than raw relevance order, so the dropdown reads as a
  // hierarchy - keyboard nav and Enter-to-select both walk this same
  // ordered list, not the flat `results` array straight off the API.
  const orderedResults = RESULT_GROUPS.flatMap((group) =>
    results.filter((result) => group.types.includes(result.type))
  );

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (mention.handleKeyDown(event, selectMention)) return;

    if (!open || orderedResults.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((prev) => (prev + 1) % orderedResults.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? orderedResults.length - 1 : prev - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const target = activeIndex >= 0 ? orderedResults[activeIndex] : orderedResults[0];
      if (target) selectResult(target);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showResultsDropdown = !mention.state.open && open && query.trim().length > 0;

  return (
    <div className="relative w-64" ref={containerRef}>
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          const value = e.target.value;
          setQuery(value);
          setOpen(true);
          scheduleSearch(value);
          mention.onTextChange(value, e.target.selectionStart ?? value.length);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder="Search everything, or ask a question... (type @ to reference something specific)"
        aria-label="Search sources, datasets, columns, glossary, processes, risks, controls, and discussions, or ask a question"
        className="w-full rounded-lg border px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-black"
      />

      {mention.state.open && (
        <MentionDropdown
          suggestions={mention.state.suggestions}
          activeIndex={mention.state.activeIndex}
          loading={mention.state.loading}
          onSelect={selectMention}
          onHover={() => {}}
        />
      )}

      {showResultsDropdown && (
        <div className="absolute left-0 top-full z-20 mt-1 w-96 max-h-96 overflow-y-auto rounded-lg border bg-white py-1 shadow-lg">
          <SearchAnswerCard
            query={query.trim()}
            answer={answer}
            asking={asking}
            onNavigate={closeDropdown}
          />

          {loading && results.length === 0 && (
            <div className="px-4 py-3 text-sm text-gray-500">Searching...</div>
          )}

          {!loading && results.length === 0 && (
            <div className="px-4 py-3 text-sm text-gray-500">
              No matches for &quot;{query.trim()}&quot;.
            </div>
          )}

          {(() => {
            let runningIndex = -1;

            return RESULT_GROUPS.map((group) => {
              const groupResults = results.filter((result) => group.types.includes(result.type));
              if (groupResults.length === 0) return null;

              return (
                <div key={group.key}>
                  <div className="px-4 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                    {group.label}
                  </div>
                  {groupResults.map((result) => {
                    runningIndex += 1;
                    const index = runningIndex;
                    return (
                      <button
                        key={`${result.type}-${result.id}`}
                        type="button"
                        onMouseEnter={() => setActiveIndex(index)}
                        onClick={() => selectResult(result)}
                        className={`block w-full px-4 py-2 text-left ${
                          index === activeIndex ? "bg-gray-50" : ""
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${ENTITY_TYPE_BADGE_CLASSES[result.type]}`}
                          >
                            {ENTITY_TYPE_LABELS[result.type]}
                          </span>
                          <span className="truncate text-sm font-medium text-gray-900">{result.label}</span>
                        </div>
                        <div className="mt-0.5 truncate text-xs text-gray-500">{result.subtitle}</div>
                        {result.snippet && (
                          <div className="mt-0.5 line-clamp-1 text-xs text-gray-400">{result.snippet}</div>
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            });
          })()}
        </div>
      )}
    </div>
  );
}
