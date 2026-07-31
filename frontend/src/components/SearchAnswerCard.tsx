"use client";

import { useRouter } from "next/navigation";

import { ENTITY_TYPE_BADGE_CLASSES, ENTITY_TYPE_LABELS } from "./entityTypeStyles";
import { askSourceHref } from "../utils/askSourceHref";
import type { AskResponse } from "../types/metadata";

type Props = {
  // The exact text that was asked - needed to deep-link "Continue in
  // Ask'Fe'" with ?q=... rather than re-typing it there.
  query: string;
  answer: AskResponse | null;
  asking: boolean;
  onNavigate?: () => void;
};

/**
 * The one piece of UI that makes "search" and "Ask'Fe'" feel like the
 * same feature instead of two separate ones: a synthesized answer,
 * grounded in the same catalog data the entity results below it come
 * from, shown inline wherever someone typed something that reads as a
 * question. Reused by both GlobalSearch's dropdown and the Ecosystem
 * page's own search panel - one rendering, not two copies that could
 * drift in what a citation link does or how the "keep going" link
 * reads.
 *
 * Doesn't replace Ask'Fe' - "Continue in Ask'Fe'" hands the exact same
 * question off to the full conversational page (history, follow-up
 * chips, download) for anyone who wants to keep going past a single
 * answer.
 */
export default function SearchAnswerCard({ query, answer, asking, onNavigate }: Props) {
  const router = useRouter();

  if (!asking && !answer) return null;

  function goTo(href: string) {
    onNavigate?.();
    router.push(href);
  }

  return (
    <div className="border-b bg-gray-50 px-4 py-3">
      <div className="mb-1.5 flex items-center justify-between">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Answer</div>
        {!asking && answer && (
          <button
            type="button"
            onClick={() => goTo(`/ask?q=${encodeURIComponent(query)}&autosubmit=1`)}
            className="text-[11px] font-medium text-blue-700 hover:text-blue-900"
          >
            Continue in Ask&apos;Fe&apos; &rarr;
          </button>
        )}
      </div>

      {asking && !answer && <div className="text-sm text-gray-500">Thinking...</div>}

      {answer && (
        <>
          <div className="whitespace-pre-line text-sm text-gray-800">{answer.answer}</div>

          {answer.sources.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {answer.sources.map((source, index) => (
                <button
                  key={`${source.type}-${source.id}-${index}`}
                  type="button"
                  onClick={() => goTo(askSourceHref(source))}
                  className="flex items-center gap-1 rounded-full border border-gray-300 bg-white px-2 py-0.5 text-[11px] text-gray-700 hover:bg-gray-100"
                >
                  <span
                    className={`rounded px-1 text-[9px] font-medium uppercase ${ENTITY_TYPE_BADGE_CLASSES[source.type]}`}
                  >
                    {ENTITY_TYPE_LABELS[source.type]}
                  </span>
                  {source.label}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
