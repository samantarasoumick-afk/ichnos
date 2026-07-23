"use client";

import { useEffect, useState } from "react";

import api from "../services/api";
import type { CertificationRequest } from "../types/metadata";

type Props = {
  datasetId: string;
  certification?: string;
  pendingRequestId?: string | null;
  canRequest: boolean;
  canApprove: boolean;
};

export default function CertificationWorkflowPanel({
  datasetId,
  certification,
  pendingRequestId,
  canRequest,
  canApprove,
}: Props) {
  const [pendingRequest, setPendingRequest] = useState<CertificationRequest | null>(null);
  const [note, setNote] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function fetchPendingRequest() {
      if (!pendingRequestId) {
        setPendingRequest(null);
        return;
      }

      try {
        const response = await api.get<CertificationRequest[]>(
          `/api/certification-requests?status=PENDING`
        );
        const match = response.data.find((r) => r.id === pendingRequestId) ?? null;
        setPendingRequest(match);
      } catch (error) {
        console.error(error);
      }
    }

    fetchPendingRequest();
  }, [pendingRequestId]);

  async function requestCertification() {
    try {
      setSubmitting(true);
      await api.post("/api/certification-requests", {
        dataset_id: datasetId,
        request_note: note || undefined,
      });
      window.location.reload();
    } catch (error) {
      console.error(error);
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail || "Failed to request certification");
    } finally {
      setSubmitting(false);
    }
  }

  async function approveRequest() {
    if (!pendingRequestId) return;
    try {
      setSubmitting(true);
      await api.post(`/api/certification-requests/${pendingRequestId}/approve`, {
        review_note: reviewNote || undefined,
      });
      window.location.reload();
    } catch (error) {
      console.error(error);
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail || "Failed to approve");
    } finally {
      setSubmitting(false);
    }
  }

  async function rejectRequest() {
    if (!pendingRequestId) return;
    try {
      setSubmitting(true);
      await api.post(`/api/certification-requests/${pendingRequestId}/reject`, {
        review_note: reviewNote || undefined,
      });
      window.location.reload();
    } catch (error) {
      console.error(error);
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail || "Failed to reject");
    } finally {
      setSubmitting(false);
    }
  }

  if (certification === "VERIFIED") {
    return (
      <div className="bg-white rounded-xl p-6 shadow">
        <h2 className="text-2xl font-semibold mb-2">Certification</h2>
        <div className="inline-block text-sm px-3 py-1 rounded-full bg-green-100 text-green-700 font-medium">
          VERIFIED
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl p-6 shadow">
      <h2 className="text-2xl font-semibold mb-4">Certification</h2>

      {!pendingRequestId && (
        <div>
          <div className="text-sm text-gray-500 mb-3">
            This dataset isn&apos;t certified yet. Certification requires review and
            approval from an admin - a steward or admin can request it below.
          </div>

          {canRequest ? (
            <div className="space-y-3">
              <textarea
                placeholder="Optional note for the reviewer"
                rows={2}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <button
                onClick={requestCertification}
                disabled={submitting}
                className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {submitting ? "Submitting..." : "Request Certification"}
              </button>
            </div>
          ) : (
            <div className="text-sm text-gray-500">
              Ask an admin or steward to request certification.
            </div>
          )}
        </div>
      )}

      {pendingRequestId && (
        <div>
          <span className="inline-block text-sm px-3 py-1 rounded-full bg-yellow-100 text-yellow-700 font-medium mb-3">
            PENDING REVIEW
          </span>

          {pendingRequest && (
            <div className="text-sm text-gray-600 space-y-1 mb-4">
              <div>Requested by: {pendingRequest.requested_by_email || "Unknown"}</div>
              {pendingRequest.request_note && (
                <div>Note: {pendingRequest.request_note}</div>
              )}
            </div>
          )}

          {canApprove ? (
            <div className="space-y-3">
              <textarea
                placeholder="Optional review note"
                rows={2}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={reviewNote}
                onChange={(event) => setReviewNote(event.target.value)}
              />
              <div className="flex items-center gap-3">
                <button
                  onClick={approveRequest}
                  disabled={submitting}
                  className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={rejectRequest}
                  disabled={submitting}
                  className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            </div>
          ) : (
            <div className="text-sm text-gray-500">
              Waiting on an admin to review this request.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
