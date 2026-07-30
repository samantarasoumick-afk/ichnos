"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type { PrivacyOverview } from "../../types/metadata";

export default function PrivacyPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [overview, setOverview] = useState<PrivacyOverview | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    async function fetchPrivacyOverview() {
      try {
        setErrorMessage(null);
        const response = await api.get<PrivacyOverview>("/api/privacy/overview");
        setOverview(response.data);
      } catch (error) {
        console.error(error);
        setErrorMessage(
          "Unable to load the privacy overview. Please make sure the backend is running."
        );
      }
    }

    fetchPrivacyOverview();
  }, [user]);

  async function handleDownloadReport() {
    setDownloading(true);
    setDownloadError(null);

    try {
      const response = await api.get("/api/reports/compliance", {
        responseType: "blob",
      });

      const url = window.URL.createObjectURL(
        new Blob([response.data], { type: "application/pdf" })
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = "compliance-report.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error(error);
      setDownloadError("Unable to generate the report right now.");
    } finally {
      setDownloading(false);
    }
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  const dpdpCategories = Object.entries(
    overview?.sensitive_columns_by_dpdp_category || {}
  ).sort((a, b) => b[1] - a[1]);

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold">Privacy</h1>
          <div className="mt-2 text-gray-600">
            DPDP/GDPR-style consent, purpose, and retention posture across your datasets.
          </div>
        </div>

        <div className="text-right">
          <button
            onClick={handleDownloadReport}
            disabled={downloading}
            className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {downloading ? "Generating..." : "Download Compliance Report"}
          </button>
          {downloadError && (
            <div className="mt-2 text-sm text-red-600">{downloadError}</div>
          )}
        </div>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Average Privacy Score</div>
          <div className="mt-2 text-4xl font-bold">
            {overview?.average_privacy_score ?? 0}
            <span className="text-lg text-gray-400">/100</span>
          </div>
        </div>

        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Needing Consent Review</div>
          <div className="mt-2 text-4xl font-bold text-yellow-600">
            {overview?.datasets_needing_consent_review ?? 0}
          </div>
        </div>

        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Overdue Retention</div>
          <div className="mt-2 text-4xl font-bold text-red-600">
            {overview?.datasets_overdue_retention ?? 0}
          </div>
        </div>

        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Missing Purpose</div>
          <div className="mt-2 text-4xl font-bold text-orange-600">
            {overview?.datasets_missing_purpose ?? 0}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-7 xl:grid-cols-[1fr_380px]">
        <section className="rounded-xl bg-white p-6 shadow">
          <h2 className="mb-4 text-2xl font-semibold">Top At-Risk Datasets</h2>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-3">Dataset</th>
                  <th className="py-3">Consent Status</th>
                  <th className="py-3">Retention</th>
                  <th className="py-3 text-right">Privacy Score</th>
                </tr>
              </thead>
              <tbody>
                {(overview?.top_at_risk_datasets || []).map((dataset) => (
                  <tr key={dataset.id} className="border-b hover:bg-gray-50">
                    <td className="py-3">
                      <Link
                        href={`/datasets/${dataset.id}`}
                        className="font-semibold"
                      >
                        {dataset.schema_name}.{dataset.name}
                      </Link>
                    </td>
                    <td className="py-3">
                      {dataset.consent_status || "NOT_ASSESSED"}
                    </td>
                    <td className="py-3">
                      <span
                        className={`
                          rounded-full px-2 py-1 text-xs
                          ${
                            dataset.retention_status === "OVERDUE"
                              ? "bg-red-100 text-red-700"
                              : dataset.retention_status === "WITHIN_POLICY"
                              ? "bg-green-100 text-green-700"
                              : "bg-gray-100 text-gray-700"
                          }
                        `}
                      >
                        {dataset.retention_status}
                      </span>
                    </td>
                    <td className="py-3 text-right font-semibold">
                      {dataset.privacy_score}/100
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {(overview?.top_at_risk_datasets || []).length === 0 && (
            <div className="py-8 text-gray-500">
              No datasets scanned yet.
            </div>
          )}
        </section>

        <section className="rounded-xl bg-white p-6 shadow">
          <h2 className="mb-4 text-2xl font-semibold">
            Sensitive Columns by DPDP Category
          </h2>

          <div className="space-y-3">
            {dpdpCategories.map(([category, count]) => (
              <div
                key={category}
                className="flex items-center justify-between rounded-lg border bg-gray-50 px-4 py-3"
              >
                <span className="text-sm capitalize">
                  {category.replace(/_/g, " ")}
                </span>
                <span className="font-semibold">{count}</span>
              </div>
            ))}

            {dpdpCategories.length === 0 && (
              <div className="rounded-lg border border-dashed p-6 text-gray-500">
                No sensitive columns detected yet.
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
