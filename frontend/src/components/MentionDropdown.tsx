"use client";

import { ENTITY_TYPE_BADGE_CLASSES, ENTITY_TYPE_LABELS } from "./entityTypeStyles";
import type { MentionItem } from "../types/metadata";

type Props = {
  suggestions: MentionItem[];
  activeIndex: number;
  loading: boolean;
  onSelect: (item: MentionItem) => void;
  onHover: (index: number) => void;
};

/**
 * The "@" mention autocomplete dropdown - shared between GlobalSearch
 * and the Ask page via useMentionPicker (frontend/src/hooks/). Purely
 * presentational: all state lives in the hook, this just renders it
 * and reports clicks/hovers back up.
 */
export default function MentionDropdown({
  suggestions,
  activeIndex,
  loading,
  onSelect,
  onHover,
}: Props) {
  if (loading && suggestions.length === 0) {
    return (
      <div className="absolute left-0 top-full z-30 mt-1 w-80 rounded-lg border bg-white py-1 shadow-lg">
        <div className="px-4 py-3 text-sm text-gray-500">Loading...</div>
      </div>
    );
  }

  if (suggestions.length === 0) {
    return (
      <div className="absolute left-0 top-full z-30 mt-1 w-80 rounded-lg border bg-white py-1 shadow-lg">
        <div className="px-4 py-3 text-sm text-gray-500">No matches.</div>
      </div>
    );
  }

  return (
    <div className="absolute left-0 top-full z-30 mt-1 w-80 max-h-72 overflow-y-auto rounded-lg border bg-white py-1 shadow-lg">
      {suggestions.map((item, index) => (
        <button
          key={`${item.type}-${item.id}`}
          type="button"
          onMouseEnter={() => onHover(index)}
          onClick={() => onSelect(item)}
          className={`flex w-full items-center gap-2 px-4 py-2 text-left ${
            index === activeIndex ? "bg-gray-50" : ""
          }`}
        >
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${ENTITY_TYPE_BADGE_CLASSES[item.type]}`}
          >
            {ENTITY_TYPE_LABELS[item.type]}
          </span>
          <span className="truncate text-sm font-medium text-gray-900">{item.label}</span>
          <span className="ml-auto shrink-0 truncate text-xs text-gray-400">{item.subtitle}</span>
        </button>
      ))}
    </div>
  );
}
