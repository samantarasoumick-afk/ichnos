"use client";

import { useMemo, useRef, useState } from "react";

import type { Dataset } from "../types/metadata";

type SchemaSuggestion = {
  kind: "schema";
  key: string;
  schema: string;
  datasetCount: number;
};

type DatasetSuggestion = {
  kind: "dataset";
  key: string;
  dataset: Dataset;
};

type Suggestion = SchemaSuggestion | DatasetSuggestion;

const MAX_SCHEMA_SUGGESTIONS = 5;
const MAX_DATASET_SUGGESTIONS = 6;

type Props = {
  datasets: Dataset[];
  value: string;
  onChange: (value: string) => void;
  onPickSchema: (schema: string) => void;
  placeholder?: string;
};

/**
 * A typeahead over a dataset list: typing suggests matching schemas
 * (pick one to filter the page down to that schema) alongside
 * matching individual datasets (pick one to narrow straight to it),
 * rather than only silently substring-filtering as you type. Kept
 * generic over a plain Dataset[] rather than fetching its own data,
 * since every page that'd use this already has the dataset list
 * loaded.
 */
export default function SchemaDatasetSearch({
  datasets,
  value,
  onChange,
  onPickSchema,
  placeholder = "Search schema or dataset...",
}: Props) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);

  const suggestions = useMemo<Suggestion[]>(() => {
    const needle = value.trim().toLowerCase();
    if (!needle) return [];

    const schemaCounts = new Map<string, number>();
    for (const dataset of datasets) {
      schemaCounts.set(dataset.schema_name, (schemaCounts.get(dataset.schema_name) ?? 0) + 1);
    }

    const schemaMatches: SchemaSuggestion[] = Array.from(schemaCounts.entries())
      .filter(([schema]) => schema.toLowerCase().includes(needle))
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(0, MAX_SCHEMA_SUGGESTIONS)
      .map(([schema, count]) => ({
        kind: "schema",
        key: `schema-${schema}`,
        schema,
        datasetCount: count,
      }));

    const datasetMatches: DatasetSuggestion[] = datasets
      .filter((dataset) => `${dataset.schema_name}.${dataset.name}`.toLowerCase().includes(needle))
      .sort((a, b) =>
        `${a.schema_name}.${a.name}`.localeCompare(`${b.schema_name}.${b.name}`)
      )
      .slice(0, MAX_DATASET_SUGGESTIONS)
      .map((dataset) => ({
        kind: "dataset",
        key: `dataset-${dataset.id}`,
        dataset,
      }));

    return [...schemaMatches, ...datasetMatches];
  }, [datasets, value]);

  function selectSuggestion(suggestion: Suggestion) {
    if (suggestion.kind === "schema") {
      onPickSchema(suggestion.schema);
      onChange("");
    } else {
      onChange(`${suggestion.dataset.schema_name}.${suggestion.dataset.name}`);
    }
    setOpen(false);
    setActiveIndex(-1);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((prev) => (prev + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const target = activeIndex >= 0 ? suggestions[activeIndex] : suggestions[0];
      if (target) selectSuggestion(target);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showDropdown = open && suggestions.length > 0;

  return (
    <div className="relative" ref={containerRef}>
      <input
        type="text"
        placeholder={placeholder}
        className="rounded-lg border px-3 py-2 text-sm"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActiveIndex(-1);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={handleKeyDown}
      />

      {showDropdown && (
        <div className="absolute left-0 top-full z-20 mt-1 w-72 max-h-80 overflow-y-auto rounded-lg border bg-white py-1 shadow-lg">
          {suggestions.map((suggestion, index) => (
            <button
              key={suggestion.key}
              type="button"
              // onMouseDown (not onClick) fires before the input's
              // onBlur closes the dropdown, so the click still lands.
              onMouseDown={(event) => {
                event.preventDefault();
                selectSuggestion(suggestion);
              }}
              onMouseEnter={() => setActiveIndex(index)}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left ${
                index === activeIndex ? "bg-gray-50" : ""
              }`}
            >
              {suggestion.kind === "schema" ? (
                <>
                  <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase bg-indigo-100 text-indigo-700">
                    Schema
                  </span>
                  <span className="truncate text-sm font-medium text-gray-900">
                    {suggestion.schema}
                  </span>
                  <span className="ml-auto shrink-0 text-xs text-gray-400">
                    {suggestion.datasetCount} dataset{suggestion.datasetCount === 1 ? "" : "s"}
                  </span>
                </>
              ) : (
                <>
                  <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase bg-blue-100 text-blue-700">
                    Dataset
                  </span>
                  <span className="truncate text-sm font-medium text-gray-900">
                    {suggestion.dataset.schema_name}.{suggestion.dataset.name}
                  </span>
                  {suggestion.dataset.domain && (
                    <span className="ml-auto shrink-0 truncate text-xs text-gray-400">
                      {suggestion.dataset.domain}
                    </span>
                  )}
                </>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
