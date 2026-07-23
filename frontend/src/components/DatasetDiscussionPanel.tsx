"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import api from "../services/api";
import type { GovernanceThread, TeamMember, ThreadType } from "../types/metadata";
import { threadTypeBadgeClasses } from "../utils/threadType";

type Props = {
  datasetId: string;
};

export default function DatasetDiscussionPanel({ datasetId }: Props) {
  const [threads, setThreads] = useState<GovernanceThread[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);

  const [showForm, setShowForm] = useState(false);
  const [threadType, setThreadType] = useState<ThreadType>("QUESTION");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [raisedForUserId, setRaisedForUserId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function fetchThreads() {
      try {
        const response = await api.get<GovernanceThread[]>(
          `/api/discussions?dataset_id=${datasetId}`
        );
        setThreads(response.data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    }

    fetchThreads();
  }, [datasetId]);

  useEffect(() => {
    async function fetchTeamMembers() {
      try {
        const response = await api.get<TeamMember[]>("/api/users");
        setTeamMembers(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    fetchTeamMembers();
  }, []);

  async function createThread() {
    if (!title.trim()) {
      alert("Give the thread a title");
      return;
    }

    try {
      setSubmitting(true);
      await api.post("/api/discussions", {
        dataset_id: datasetId,
        thread_type: threadType,
        title,
        body: body || undefined,
        raised_for_user_id:
          threadType === "ISSUE" && raisedForUserId ? raisedForUserId : undefined,
      });
      const response = await api.get<GovernanceThread[]>(
        `/api/discussions?dataset_id=${datasetId}`
      );
      setThreads(response.data);
      setTitle("");
      setBody("");
      setRaisedForUserId("");
      setShowForm(false);
    } catch (error) {
      console.error(error);
      alert("Failed to start thread");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="bg-white rounded-xl p-6 shadow">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-semibold">Discussion</h2>
        <button
          onClick={() => setShowForm((value) => !value)}
          className="text-sm rounded-lg border px-3 py-1.5 hover:bg-gray-50"
        >
          {showForm ? "Cancel" : "Ask, Propose, or Raise Issue"}
        </button>
      </div>

      {showForm && (
        <div className="mb-4 space-y-2 border rounded-lg p-4">
          <select
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={threadType}
            onChange={(event) => setThreadType(event.target.value as ThreadType)}
          >
            <option value="QUESTION">Question</option>
            <option value="PROPOSAL">Proposal</option>
            <option value="ISSUE">Issue</option>
          </select>
          <input
            type="text"
            placeholder="Title"
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <textarea
            placeholder="Details (optional)"
            rows={2}
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={body}
            onChange={(event) => setBody(event.target.value)}
          />
          {threadType === "ISSUE" && (
            <select
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={raisedForUserId}
              onChange={(event) => setRaisedForUserId(event.target.value)}
            >
              <option value="">Raise for (optional stakeholder)</option>
              {teamMembers
                .slice()
                .sort((a, b) => a.email.localeCompare(b.email))
                .map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.email} ({member.role.replace("_", " ")})
                  </option>
                ))}
            </select>
          )}
          <button
            onClick={createThread}
            disabled={submitting}
            className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {submitting ? "Posting..." : "Post"}
          </button>
        </div>
      )}

      {loading && <div className="text-sm text-gray-500">Loading...</div>}

      {!loading && threads.length === 0 && (
        <div className="text-sm text-gray-500">
          No discussion on this dataset yet.
        </div>
      )}

      {!loading && threads.length > 0 && (
        <div className="space-y-2">
          {threads.slice(0, 5).map((thread) => (
            <Link
              key={thread.id}
              href={`/discussions/${thread.id}`}
              className="block rounded-lg border p-3 text-sm hover:bg-gray-50"
            >
              <div className="flex items-center gap-2 mb-1">
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
              </div>
              {thread.title}
            </Link>
          ))}

          {threads.length > 5 && (
            <Link
              href={`/discussions?dataset_id=${datasetId}`}
              className="block text-center text-xs text-gray-500 hover:underline pt-1"
            >
              View all {threads.length} threads
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
