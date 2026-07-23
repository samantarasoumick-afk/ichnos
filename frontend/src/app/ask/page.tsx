"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type { AskResponse, AskSource } from "../../types/metadata";

type ConversationEntry = {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: AskSource[];
};

const EXAMPLE_QUESTIONS = [
  "Which datasets have PII?",
  "Who owns customers?",
  "What's downstream of orders?",
  "How's our governance maturity?",
  "Do we have any contract breaches?",
];

function sourceHref(source: AskSource) {
  if (source.type === "dataset") {
    return `/datasets/${source.id}`;
  }
  return "/governance";
}

export default function AskPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const nextEntryId = useRef(0);

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

    const header = `Ichnos - Ask conversation\nExported ${new Date().toLocaleString()}\n\n`;
    const blob = new Blob([header + lines.join("\n\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `ichnos-ask-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

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
      const response = await api.post<AskResponse>("/api/assistant/ask", { query: trimmed });

      const assistantEntry: ConversationEntry = {
        id: `${newEntryId()}-assistant`,
        role: "assistant",
        text: response.data.answer,
        sources: response.data.sources,
      };

      setConversation((prev) => [...prev, assistantEntry]);
    } catch (error) {
      console.error(error);
      setErrorMessage("Unable to reach the assistant right now.");
    } finally {
      setAsking(false);
    }
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

      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold">Ask</h1>
          <p className="mt-2 text-gray-600">
            Ask questions about your catalog in plain English - ownership, sensitivity,
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
                        href={sourceHref(source)}
                        className="text-xs underline text-blue-700 hover:text-blue-900"
                      >
                        {source.label}
                      </Link>
                    ))}
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
          <input
            type="text"
            placeholder="Ask about your catalog..."
            className="flex-1 rounded-lg border px-3 py-2 text-sm"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                submitQuestion(question);
              }
            }}
          />
          <button
            onClick={() => submitQuestion(question)}
            disabled={asking || !question.trim()}
            className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
          >
            Ask
          </button>
        </div>
      </div>
    </main>
  );
}
