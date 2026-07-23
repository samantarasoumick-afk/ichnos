"use client";

import { useEffect, useState } from "react";

import Link from "next/link";

import api from "../services/api";
import type { CertificationRequest, Dataset } from "../types/metadata";

type Props = {
  datasets: Dataset[];
  canReview: boolean;
};

export default function CertificationQueue({ datasets, canReview }: Props) {
  const [requests, setRequests] = useState<CertificationRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [submittingId, setSubmittingId] = useState<string | null>(null);

  useEffect(() => {
    async function fetchQueue() {
      try {
        const response = await api.get<CertificationRequest[]>(
          "/api/certification-requests?status=PENDING"
        );
        setRequests(response.data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    }

    fetchQueue();
  }, []);

  function datasetLabel(datasetId: string) {
    const dataset = datasets.find((d) => d.id === datasetId);
    return dataset ? `${dataset.schema_name}.${dataset.name}` : datasetId;
  }

  async function approve(requestId: string) {
    try {
      setSubmittingId(requestId);
      await api.post(`/api/certification-requests/${requestId}/approve`, {
        review_note: reviewNotes[requestId] || undefined,
      });
      setRequests((prev) => prev.filter((r) => r.id !== requestId));
    } catch (error) {
      console.error(error);
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail || "Failed to approve");
    } finally {
      setSubmittingId(null);
    }
  }

  async function reject(requestId: string) {
    try {
      setSubmittingId(requestId);
      await api.post(`/api/certification-requests/${requestId}/reject`, {
        review_note: reviewNotes[requestId] || undefined,
      });
      setRequests((prev) => prev.filter((r) => r.id !== requestId));
    } catch (error) {
      console.error(error);
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail || "Failed to reject");
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <section className="rounded-xl bg-white p-6 shadow mb-8">
      <h2 className="mb-4 text-2xl font-semibold">Certification Queue</h2>

      {loading && <div className="text-gray-500">Loading...</div>}

      {!loading && requests.length === 0 && (
        <div className="text-gray-500 text-sm">No pending certification requests.</div>
      )}

      <div className="space-y-4">
        {requests.map((request) => (
          <div key={request.id} className="border rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div>
                <Link
                  href={`/datasets/${request.dataset_id}`}
                  className="font-semibold hover:underline"
                >
                  {datasetLabel(request.dataset_id)}
                </Link>
                <div className="text-xs text-gray-500 mt-1">
                  Requested by {request.requested_by_email || "unknown"}
                </div>
                {request.request_note && (
                  <div className="text-sm text-gray-600 mt-2">{request.request_note}</div>
                )}
              </div>
            </div>

            {canReview && (
              <div className="mt-3 space-y-2">
                <textarea
                  placeholder="Optional review note"
                  rows={2}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={reviewNotes[request.id] ?? ""}
                  onChange={(event) =>
                    setReviewNotes((prev) => ({ ...prev, [request.id]: event.target.value }))
                  }
                />
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => approve(request.id)}
                    disabled={submittingId === request.id}
                    className="rounded-lg bg-black px-3 py-1.5 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => reject(request.id)}
                    disabled={submittingId === request.id}
                    className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
