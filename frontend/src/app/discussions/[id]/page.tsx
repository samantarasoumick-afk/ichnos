"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import TopNav from "../../../components/TopNav";
import { useRequireAuth } from "../../../hooks/useRequireAuth";
import api from "../../../services/api";
import type { GovernanceThreadDetail } from "../../../types/metadata";
import { threadTypeBadgeClasses } from "../../../utils/threadType";

function formatDate(iso?: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

export default function DiscussionThreadPage() {
  const { user, loading: authLoading } = useRequireAuth();
  const params = useParams<{ id: string }>();
  const threadId = params.id;

  const [thread, setThread] = useState<GovernanceThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [replyBody, setReplyBody] = useState("");
  const [posting, setPosting] = useState(false);

  const [resolutionNote, setResolutionNote] = useState("");
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    if (!user || !threadId) return;

    async function fetchThread() {
      try {
        setErrorMessage(null);
        const response = await api.get<GovernanceThreadDetail>(
          `/api/discussions/${threadId}`
        );
        setThread(response.data);
      } catch (error) {
        console.error(error);
        setErrorMessage("Unable to load this discussion.");
      } finally {
        setLoading(false);
      }
    }

    fetchThread();
  }, [user, threadId]);

  async function postReply() {
    if (!replyBody.trim()) return;

    try {
      setPosting(true);
      const response = await api.post<GovernanceThreadDetail>(
        `/api/discussions/${threadId}/replies`,
        { body: replyBody }
      );
      setThread(response.data);
      setReplyBody("");
    } catch (error) {
      console.error(error);
      alert("Failed to post reply");
    } finally {
      setPosting(false);
    }
  }

  async function resolveThread() {
    try {
      setResolving(true);
      const response = await api.post<GovernanceThreadDetail>(
        `/api/discussions/${threadId}/resolve`,
        { resolution_note: resolutionNote || undefined }
      );
      setThread(response.data);
    } catch (error) {
      console.error(error);
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail || "Failed to resolve thread");
    } finally {
      setResolving(false);
    }
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-lg bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  const canResolve =
    !!thread &&
    thread.status === "OPEN" &&
    (thread.created_by === user.id || user.role === "admin" || user.role === "steward");

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <Link href="/discussions" className="text-sm text-gray-500 hover:text-black">
        &larr; Back to Discussions
      </Link>

      {errorMessage && (
        <div className="mt-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {loading && (
        <div className="mt-6 rounded-lg bg-white p-6 shadow">Loading...</div>
      )}

      {!loading && thread && (
        <>
          <div className="mt-6 rounded-xl bg-white p-6 shadow">
            <div className="flex items-center gap-2 mb-2">
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${threadTypeBadgeClasses(
                  thread.thread_type
                )}`}
              >
                {thread.thread_type}
              </span>
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                  thread.status === "RESOLVED"
                    ? "bg-green-100 text-green-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {thread.status}
              </span>
              {thread.dataset_id && thread.dataset_label && (
                <Link
                  href={`/datasets/${thread.dataset_id}`}
                  className="text-xs text-gray-400 hover:underline"
                >
                  {thread.dataset_label}
                </Link>
              )}
            </div>

            <h1 className="text-2xl font-bold">{thread.title}</h1>
            <div className="mt-1 text-xs text-gray-400">
              Opened by {thread.created_by_email} &middot; {formatDate(thread.created_at)}
            </div>

            {thread.body && <p className="mt-4 text-sm text-gray-700">{thread.body}</p>}

            {thread.raised_for_email && (
              <div className="mt-3 inline-block rounded-lg bg-orange-50 px-3 py-1.5 text-sm text-orange-800">
                Raised for follow-through with {thread.raised_for_email}
              </div>
            )}

            {thread.status === "RESOLVED" && (
              <div className="mt-4 rounded-lg bg-green-50 p-3 text-sm text-green-800">
                Resolved by {thread.resolved_by_email} &middot; {formatDate(thread.resolved_at ?? undefined)}
                {thread.resolution_note && (
                  <div className="mt-1">{thread.resolution_note}</div>
                )}
              </div>
            )}

            {canResolve && (
              <div className="mt-4 border-t pt-4 space-y-2">
                <textarea
                  placeholder="Optional resolution note"
                  rows={2}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={resolutionNote}
                  onChange={(event) => setResolutionNote(event.target.value)}
                />
                <button
                  onClick={resolveThread}
                  disabled={resolving}
                  className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
                >
                  {resolving ? "Resolving..." : "Mark Resolved"}
                </button>
              </div>
            )}
          </div>

          <div className="mt-6 space-y-3">
            {thread.replies.map((reply) => (
              <div key={reply.id} className="rounded-xl bg-white p-4 shadow">
                <div className="text-xs text-gray-400 mb-1">
                  {reply.created_by_email} &middot; {formatDate(reply.created_at)}
                </div>
                <div className="text-sm text-gray-700 whitespace-pre-wrap">{reply.body}</div>
              </div>
            ))}
            {thread.replies.length === 0 && (
              <div className="rounded-xl bg-white p-4 shadow text-sm text-gray-500">
                No replies yet.
              </div>
            )}
          </div>

          <div className="mt-6 rounded-xl bg-white p-6 shadow">
            <textarea
              placeholder="Write a reply..."
              rows={3}
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={replyBody}
              onChange={(event) => setReplyBody(event.target.value)}
            />
            <button
              onClick={postReply}
              disabled={posting || !replyBody.trim()}
              className="mt-3 rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
            >
              {posting ? "Posting..." : "Reply"}
            </button>
          </div>
        </>
      )}
    </main>
  );
}
