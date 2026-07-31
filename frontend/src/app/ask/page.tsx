"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import MentionDropdown from "../../components/MentionDropdown";
import TopNav from "../../components/TopNav";
import { useMentionPicker } from "../../hooks/useMentionPicker";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import { askSourceHref } from "../../utils/askSourceHref";
import type { AskFollowUpSuggestion, AskResponse, AskSource, MentionItem } from "../../types/metadata";

type ConversationEntry = {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: AskSource[];
  followUpSuggestions?: AskFollowUpSuggestion[];
};

const EXAMPLE_QUESTIONS = [
  "Which datasets have PII?",
  "Who owns customers?",
  "What's downstream of orders?",
  "How's our governance maturity?",
  "Do we have any contract breaches?",
];

export default function AskPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const nextEntryId = useRef(0);
  const questionInputRef = useRef<HTMLInputElement>(null);
  const mention = useMentionPicker();

  function selectMention(item: MentionItem) {
    const el = questionInputRef.current;
    const caret = el?.selectionStart ?? question.length;
    const inserted = mention.buildInsertion(question, caret, item);

    mention.close();

    if (!inserted) return;

    setQuestion(inserted.value);

    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(inserted.caret, inserted.caret);
    });
  }

  function newEntryId() {
    nextEntryId.current += 1;
    return nextEntryId.current;
  }

  function clearConversation() {
    setConversation([]);
    setErrorMessage(null);
  }

  function downloadConversation() {
    const lines = conversation.map((entry) => {
      const speaker = entry.role === "user" ? "You" : "Assistant";
      const sourceLines =
        entry.sources && entry.sources.length > 0
          ? "\n" + entry.sources.map((source) => `  Source: ${source.label}`).join("\n")
          : "";
      return `${speaker}: ${entry.text}${sourceLines}`;
    });

    const header = `DatFe - Ask'Fe' conversation\nExported ${new Date().toLocaleString()}\n\n`;
    const blob = new Blob([header + lines.join("\n\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `datafe-askfe-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  // Deep-linkable from the guided tour (?q=who owns customers?&autosubmit=1)
  // - runs once after the user's loaded, rather than reading
  // window.location.search into initial state, since submitting needs
  // submitQuestion (defined below) to exist first. Guarded with a ref
  // so a re-render (e.g. from asking-state changes) never re-fires it.
  const ranDeepLinkRef = useRef(false);
  useEffect(() => {
    if (authLoading || !user || ranDeepLinkRef.current) return;
    ranDeepLinkRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const prefill = params.get("q");
    if (!prefill) return;

    if (params.get("autosubmit") === "1") {
      submitQuestion(prefill);
    } else {
      // Deferred a tick rather than called synchronously in the
      // effect body, same reasoning as react-hooks/set-state-in-effect
      // recommends - this is a one-time prefill from an external
      // source (the URL), not state React should own the timing of.
      queueMicrotask(() => setQuestion(prefill));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  async function submitQuestion(text: string) {
    const trimmed = text.trim();
    if (!trimmed || asking) return;

    const userEntry: ConversationEntry = {
      id: `${newEntryId()}-user`,
      role: "user",
      text: trimmed,
    };

    setConversation((prev) => [...prev, userEntry]);
    setQuestion("");
    setAsking(true);
    setErrorMessage(null);

    try {
      const response = await api.post<AskResponse>("/api/assistant/ask", {
        query: trimmed,
        // Prior turns only - the new question above isn't part of history,
        // it's the current query. Lets follow-up questions ("what about
        // its downstream tables?") resolve against what was already asked.
        history: conversation.map((entry) => ({ role: entry.role, text: entry.text })),
      });

      const assistantEntry: ConversationEntry = {
        id: `${newEntryId()}-assistant`,
        role: "assistant",
        text: response.data.answer,
        sources: response.data.sources,
        followUpSuggestions: response.data.follow_up_suggestions,
      };

      setConversation((prev) => [...prev, assistantEntry]);
    } catch (error) {
      console.error(error);

      // Surface the backend's actual detail when there is one (e.g. a
      // 429 from the daily Ask'Fe' quota - "Your Free plan includes 20
      // Ask'Fe' questions per day...") instead of always showing the
      // same generic string, which used to swallow that message
      // entirely and make a plan limit look like a network outage.
      // Same pattern used elsewhere in the app (DemoDataPanel,
      // CertificationQueue, etc.)
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

      setErrorMessage(detail || "Unable to reach the assistant right now.");
    } finally {
      setAsking(false);
    }
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

      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold">Ask&apos;Fe&apos;</h1>
          <p className="mt-2 text-gray-600">
            Ask&apos;Fe&apos; questions about your catalog in plain English - ownership, sensitivity,
            lineage, governance standing, and contract health are answered directly from
            your data.
          </p>
        </div>

        {conversation.length > 0 && (
          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={downloadConversation}
              className="rounded-lg border bg-white px-3 py-2 text-sm hover:bg-gray-50"
            >
              Download
            </button>
            <button
              onClick={clearConversation}
              className="rounded-lg border bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      <div className="rounded-xl bg-white shadow flex flex-col" style={{ minHeight: "60vh" }}>
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {conversation.length === 0 && (
            <div>
              <div className="text-gray-500 mb-3 text-sm">Try one of these:</div>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_QUESTIONS.map((example) => (
                  <button
                    key={example}
                    onClick={() => submitQuestion(example)}
                    className="rounded-full border px-3 py-1.5 text-sm hover:bg-gray-50"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}

          {conversation.map((entry) => (
            <div
              key={entry.id}
              className={`flex ${entry.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`
                  max-w-2xl rounded-xl px-4 py-3 text-sm whitespace-pre-line
                  ${entry.role === "user" ? "bg-black text-white" : "bg-gray-100 text-gray-800"}
                `}
              >
                {entry.text}

                {entry.sources && entry.sources.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2 border-t border-gray-300 pt-2">
                    {entry.sources.map((source, index) => (
                      <Link
                        key={`${source.id}-${index}`}
                        href={askSourceHref(source)}
                        className="text-xs underline text-blue-700 hover:text-blue-900"
                      >
                        {source.label}
                      </Link>
                    ))}
                  </div>
                )}

                {entry.followUpSuggestions && entry.followUpSuggestions.length > 0 && (
                  <div className="mt-3 border-t border-gray-300 pt-2">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                      Keep going
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {entry.followUpSuggestions.map((suggestion, index) => (
                        <button
                          key={`${suggestion.label}-${index}`}
                          type="button"
                          onClick={() => submitQuestion(suggestion.query)}
                          disabled={asking}
                          className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        >
                          {suggestion.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {asking && (
            <div className="flex justify-start">
              <div className="rounded-xl bg-gray-100 px-4 py-3 text-sm text-gray-500">
                Thinking...
              </div>
            </div>
          )}

          {errorMessage && (
            <div className="text-red-600 text-sm">{errorMessage}</div>
          )}
        </div>

        <div className="border-t p-4 flex items-center gap-3">
          <div className="relative flex-1">
            <input
              ref={questionInputRef}
              type="text"
              placeholder="Ask about your catalog... (type @ to reference something specific)"
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={question}
              onChange={(event) => {
                const value = event.target.value;
                setQuestion(value);
                mention.onTextChange(value, event.target.selectionStart ?? value.length);
              }}
              onKeyDown={(event) => {
                if (mention.handleKeyDown(event, selectMention)) return;

                if (event.key === "Enter") {
                  submitQuestion(question);
                }
              }}
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
          </div>
          <button
            onClick={() => submitQuestion(question)}
            disabled={asking || !question.trim()}
            className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
          >
            Ask&apos;Fe&apos;
          </button>
        </div>
      </div>
    </main>
  );
}
