"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type {
  Dataset,
  GovernanceThread,
  TeamMember,
  ThreadType,
} from "../../types/metadata";
import { threadTypeBadgeClasses } from "../../utils/threadType";

type StatusFilter = "OPEN" | "RESOLVED" | "ALL";
type TypeFilter = ThreadType | "ALL";

function timeAgo(iso?: string) {
  if (!iso) return "";
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function DiscussionsPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [threads, setThreads] = useState<GovernanceThread[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("OPEN");
  // Read once, lazily, rather than via useSearchParams() (which in
  // the Next.js app router requires a Suspense boundary even for a
  // fully client-rendered page like this one) or an effect (which
  // would call setState synchronously on mount). window is undefined
  // during any server-side render pass, hence the guard - matches the
  // pattern AuthContext already uses for localStorage. Lets TopNav
  // (and anywhere else) deep-link straight to a filtered view, e.g.
  // /discussions?thread_type=issue.
  const [typeFilter, setTypeFilter] = useState<TypeFilter>(() => {
    if (typeof window === "undefined") return "ALL";
    const raw = new URLSearchParams(window.location.search).get("thread_type");
    const upper = raw?.toUpperCase();
    return upper === "QUESTION" || upper === "PROPOSAL" || upper === "ISSUE" ? upper : "ALL";
  });
  const [datasetIdFilter, setDatasetIdFilter] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return new URLSearchParams(window.location.search).get("dataset_id");
  });

  const [showForm, setShowForm] = useState(false);
  const [newThreadType, setNewThreadType] = useState<ThreadType>("QUESTION");
  const [newDatasetId, setNewDatasetId] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [newRaisedForUserId, setNewRaisedForUserId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function fetchThreads() {
    try {
      setLoading(true);
      setErrorMessage(null);
      const params = new URLSearchParams();
      if (statusFilter !== "ALL") params.set("status", statusFilter);
      if (typeFilter !== "ALL") params.set("thread_type", typeFilter);
      if (datasetIdFilter) params.set("dataset_id", datasetIdFilter);

      const response = await api.get<GovernanceThread[]>(
        `/api/discussions?${params.toString()}`
      );
      setThreads(response.data);
    } catch (error) {
      console.error(error);
      setErrorMessage(
        "Unable to load discussions. Please make sure the backend is running on http://127.0.0.1:8000."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!user) return;

    async function loadThreads() {
      await fetchThreads();
    }

    loadThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, statusFilter, typeFilter, datasetIdFilter]);

  useEffect(() => {
    if (!user) return;

    async function fetchDatasets() {
      try {
        const response = await api.get<Dataset[]>("/api/datasets");
        setDatasets(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    fetchDatasets();
  }, [user]);

  useEffect(() => {
    if (!user) return;

    async function fetchTeamMembers() {
      try {
        const response = await api.get<TeamMember[]>("/api/users");
        setTeamMembers(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    fetchTeamMembers();
  }, [user]);

  async function createThread() {
    if (!newTitle.trim()) {
      alert("Give the thread a title");
      return;
    }

    try {
      setSubmitting(true);
      await api.post("/api/discussions", {
        thread_type: newThreadType,
        dataset_id: newDatasetId || undefined,
        title: newTitle,
        body: newBody || undefined,
        raised_for_user_id:
          newThreadType === "ISSUE" && newRaisedForUserId ? newRaisedForUserId : undefined,
      });
      setNewTitle("");
      setNewBody("");
      setNewDatasetId("");
      setNewRaisedForUserId("");
      setShowForm(false);
      await fetchThreads();
    } catch (error) {
      console.error(error);
      alert("Failed to create thread");
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-lg bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  const datasetById = new Map(datasets.map((dataset) => [dataset.id, dataset]));

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold">Discussions</h1>
          <p className="mt-2 text-gray-600">
            Questions, proposals, and issues between the people who use and steward
            this catalog - the fastest way to resolve &quot;what does this actually
            mean?&quot; or raise something for follow-through, without leaving the
            platform.
          </p>
        </div>
        <button
          onClick={() => setShowForm((value) => !value)}
          className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800"
        >
          {showForm ? "Cancel" : "New Thread"}
        </button>
      </div>

      {showForm && (
        <div className="mb-8 rounded-xl bg-white p-6 shadow">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="text-sm text-gray-500 block mb-1">Type</label>
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newThreadType}
                onChange={(event) => setNewThreadType(event.target.value as ThreadType)}
              >
                <option value="QUESTION">Question</option>
                <option value="PROPOSAL">Proposal</option>
                <option value="ISSUE">Issue</option>
              </select>
            </div>

            <div>
              <label className="text-sm text-gray-500 block mb-1">
                Dataset (optional)
              </label>
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newDatasetId}
                onChange={(event) => setNewDatasetId(event.target.value)}
              >
                <option value="">General / not dataset-specific</option>
                {datasets
                  .slice()
                  .sort((a, b) =>
                    `${a.schema_name}.${a.name}`.localeCompare(`${b.schema_name}.${b.name}`)
                  )
                  .map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>
                      {dataset.schema_name}.{dataset.name}
                    </option>
                  ))}
              </select>
            </div>

            <div className="md:col-span-2">
              <label className="text-sm text-gray-500 block mb-1">Title</label>
              <input
                type="text"
                placeholder="Keep it short - the actual discussion goes below"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newTitle}
                onChange={(event) => setNewTitle(event.target.value)}
              />
            </div>

            <div className="md:col-span-2">
              <label className="text-sm text-gray-500 block mb-1">
                Details (optional)
              </label>
              <textarea
                rows={3}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={newBody}
                onChange={(event) => setNewBody(event.target.value)}
              />
            </div>

            {newThreadType === "ISSUE" && (
              <div className="md:col-span-2">
                <label className="text-sm text-gray-500 block mb-1">
                  Raise for (optional) - the stakeholder who should follow through
                </label>
                <select
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={newRaisedForUserId}
                  onChange={(event) => setNewRaisedForUserId(event.target.value)}
                >
                  <option value="">No specific stakeholder</option>
                  {teamMembers
                    .slice()
                    .sort((a, b) => a.email.localeCompare(b.email))
                    .map((member) => (
                      <option key={member.id} value={member.id}>
                        {member.email} ({member.role.replace("_", " ")})
                      </option>
                    ))}
                </select>
              </div>
            )}
          </div>

          <button
            onClick={createThread}
            disabled={submitting}
            className="mt-4 rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {submitting ? "Posting..." : "Post"}
          </button>
        </div>
      )}

      {datasetIdFilter && (
        <div className="mb-4 flex items-center gap-2 text-sm">
          <span className="text-gray-500">
            Filtered to {datasetById.get(datasetIdFilter)?.schema_name}.
            {datasetById.get(datasetIdFilter)?.name ?? datasetIdFilter}
          </span>
          <button
            onClick={() => setDatasetIdFilter(null)}
            className="text-gray-500 underline hover:text-black"
          >
            Clear
          </button>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border bg-white text-sm overflow-hidden">
          {(["OPEN", "RESOLVED", "ALL"] as StatusFilter[]).map((option) => (
            <button
              key={option}
              onClick={() => setStatusFilter(option)}
              className={`px-3 py-1.5 ${
                statusFilter === option ? "bg-black text-white" : "hover:bg-gray-50"
              }`}
            >
              {option === "ALL" ? "All" : option === "OPEN" ? "Open" : "Resolved"}
            </button>
          ))}
        </div>

        <div className="flex rounded-lg border bg-white text-sm overflow-hidden">
          {(["ALL", "QUESTION", "PROPOSAL", "ISSUE"] as TypeFilter[]).map((option) => (
            <button
              key={option}
              onClick={() => setTypeFilter(option)}
              className={`px-3 py-1.5 ${
                typeFilter === option ? "bg-black text-white" : "hover:bg-gray-50"
              }`}
            >
              {option === "ALL"
                ? "All types"
                : option === "QUESTION"
                ? "Questions"
                : option === "PROPOSAL"
                ? "Proposals"
                : "Issues"}
            </button>
          ))}
        </div>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {loading && (
        <div className="rounded-lg bg-white p-6 shadow">Loading discussions...</div>
      )}

      {!loading && !errorMessage && threads.length === 0 && (
        <div className="rounded-lg bg-white p-6 shadow text-gray-500">
          No discussions here yet. Start one above.
        </div>
      )}

      {!loading && !errorMessage && threads.length > 0 && (
        <div className="space-y-3">
          {threads.map((thread) => (
            <Link
              key={thread.id}
              href={`/discussions/${thread.id}`}
              className="block rounded-xl bg-white p-5 shadow hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
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
                    {thread.dataset_id && (
                      <span className="text-xs text-gray-400">
                        {thread.dataset_label ?? datasetById.get(thread.dataset_id)?.name}
                      </span>
                    )}
                  </div>
                  <div className="font-medium">{thread.title}</div>
                  {thread.body && (
                    <div className="mt-1 text-sm text-gray-500 line-clamp-2">
                      {thread.body}
                    </div>
                  )}
                  {thread.raised_for_email && (
                    <div className="mt-1 text-xs text-orange-700">
                      Raised for {thread.raised_for_email}
                    </div>
                  )}
                </div>
                <div className="text-right text-xs text-gray-400 shrink-0">
                  <div>{thread.created_by_email}</div>
                  <div>{timeAgo(thread.created_at)}</div>
                  <div className="mt-1">
                    {thread.reply_count} {thread.reply_count === 1 ? "reply" : "replies"}
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
