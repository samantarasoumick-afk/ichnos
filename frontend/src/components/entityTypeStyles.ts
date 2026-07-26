import type { SearchResultType } from "../types/metadata";

// Shared between GlobalSearch's results dropdown and MentionDropdown's
// "@" picker - both show the same six entity types and should look
// like the same visual language, not drift independently.
export const ENTITY_TYPE_LABELS: Record<SearchResultType, string> = {
  dataset: "Dataset",
  glossary_term: "Glossary",
  process: "Process",
  risk: "Risk",
  control: "Control",
  discussion_thread: "Discussion",
};

export const ENTITY_TYPE_BADGE_CLASSES: Record<SearchResultType, string> = {
  dataset: "bg-blue-100 text-blue-700",
  glossary_term: "bg-purple-100 text-purple-700",
  process: "bg-emerald-100 text-emerald-700",
  risk: "bg-red-100 text-red-700",
  control: "bg-amber-100 text-amber-700",
  discussion_thread: "bg-gray-200 text-gray-700",
};
