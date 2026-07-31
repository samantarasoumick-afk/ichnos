import api from "../services/api";
import type { AskResponse } from "../types/metadata";

// The shared "engine" behind unified search: one heuristic for "does
// this look like a question rather than a bare lookup term", and one
// thin call to the exact same Ask'Fe' endpoint the dedicated
// conversation page uses. Both GlobalSearch (the top-nav bar) and the
// Ecosystem page's own search box import this rather than each
// growing their own copy - the whole point of unifying search is that
// there's one place that decides "is this a question", not three.

// Interrogative openers common enough in real catalog questions
// ("who owns X", "does X have PII", "is X certified") to be a useful
// signal even without a trailing "?" - people often don't bother
// typing the question mark in a search box.
const INTERROGATIVE_STARTERS = new Set([
  "who",
  "whose",
  "what",
  "when",
  "where",
  "why",
  "how",
  "which",
  "does",
  "do",
  "did",
  "is",
  "are",
  "was",
  "were",
  "can",
  "could",
  "should",
  "would",
  "will",
  "has",
  "have",
]);

export function isQuestionLike(query: string): boolean {
  const trimmed = query.trim();
  if (!trimmed) return false;

  if (trimmed.endsWith("?")) return true;

  const firstWord = trimmed.split(/\s+/)[0]?.toLowerCase().replace(/[^a-z']/g, "");
  return firstWord ? INTERROGATIVE_STARTERS.has(firstWord) : false;
}

// Never throws - a failed/errored inline answer just means the answer
// card doesn't render; the entity results (which come from a separate
// call) are unaffected either way. Single-turn on purpose (empty
// history): this is a fresh, one-off lookup from a search box, not a
// continuation of the Ask'Fe' page's own conversation - "Continue in
// Ask'Fe'" is what promotes it into a real multi-turn thread.
export async function fetchInlineAnswer(query: string): Promise<AskResponse | null> {
  try {
    const response = await api.post<AskResponse>("/api/assistant/ask", {
      query,
      history: [],
    });
    return response.data;
  } catch (error) {
    console.error(error);
    return null;
  }
}
