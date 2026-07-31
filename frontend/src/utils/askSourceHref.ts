import type { AskSource } from "../types/metadata";

// Shared by the Ask'Fe' page and the unified search answer card (see
// SearchAnswerCard.tsx) so a citation routes identically wherever it's
// clicked from - one function, not two copies quietly drifting apart.
//
// `source.url` is populated whenever the answer came from the
// semantic-search fallback (assistant_service.py's
// _answer_via_semantic_search), which covers all 8 catalog entity
// types via the exact same describe_document() helper GET /api/search
// uses - so that's authoritative and used first. The hand-built intent
// handlers (ownership/quality/glossary/process/...) don't set a url
// yet, so this falls back to the same type-based guesses this app used
// before that field existed.
export function askSourceHref(source: AskSource): string {
  if (source.url) {
    return source.url;
  }

  if (source.type === "dataset") {
    return `/datasets/${source.id}`;
  }
  if (source.type === "source") {
    return `/ecosystem?sourceId=${source.id}`;
  }
  if (source.type === "process") {
    return "/processes";
  }

  return "/governance";
}
