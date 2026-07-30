"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import CertificationQueue from "../../components/CertificationQueue";
import MaturityPanel from "../../components/MaturityPanel";
import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type { Dataset, GovernanceOverview } from "../../types/metadata";

export default function GovernancePage() {
  const { user, loading: authLoading, effectiveRole } = useRequireAuth();

  const [overview, setOverview] = useState<GovernanceOverview | null>(null);
  const [scorecards, setScorecards] = useState<Dataset[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    async function fetchGovernance() {
      try {
        setErrorMessage(null);

        const [overviewResponse, scorecardResponse] = await Promise.all([
          api.get<GovernanceOverview>("/api/governance/overview"),
          api.get<Dataset[]>("/api/governance/scorecards"),
        ]);

        setOverview(overviewResponse.data);
        setScorecards(
          [...scorecardResponse.data].sort((a, b) => {
            return (a.governance_score || 0) - (b.governance_score || 0);
          })
        );
      } catch (error) {
        console.error(error);
        setErrorMessage(
          "Unable to load governance. Please make sure the backend is running on http://127.0.0.1:8000."
        );
      }
    }

    fetchGovernance();
  }, [user]);

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

      <div className="mb-8">
        <h1 className="text-4xl font-bold">Governance</h1>
        <div className="mt-2 text-gray-600">
          Stewardship, ownership, certifications, and governance scoring.
        </div>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      <MaturityPanel />

      <CertificationQueue
        datasets={scorecards}
        canReview={effectiveRole === "admin" || effectiveRole === "data_owner"}
      />

      <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-3 xl:grid-cols-6">
        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Datasets</div>
          <div className="mt-2 text-4xl font-bold">
            {overview?.total_datasets || 0}
          </div>
        </div>

        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Average Score</div>
          <div className="mt-2 text-4xl font-bold">
            {overview?.average_governance_score || 0}
          </div>
        </div>

        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Missing Stewards</div>
          <div className="mt-2 text-4xl font-bold text-yellow-600">
            {overview?.missing_stewards || 0}
          </div>
        </div>

        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Uncertified</div>
          <div className="mt-2 text-4xl font-bold text-orange-600">
            {overview?.uncertified_datasets || 0}
          </div>
        </div>

        <div className="rounded-xl bg-white p-6 shadow">
          <div className="text-sm text-gray-500">Critical</div>
          <div className="mt-2 text-4xl font-bold text-red-600">
            {overview?.critical_datasets || 0}
          </div>
        </div>

        <Link href="/glossary" className="rounded-xl bg-white p-6 shadow hover:bg-gray-50">
          <div className="text-sm text-gray-500">Glossary Terms</div>
          <div className="mt-2 text-4xl font-bold">
            {overview?.glossary_terms || 0}
          </div>
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-7 xl:grid-cols-[1fr_320px]">
        <section className="rounded-xl bg-white p-6 shadow">
          <h2 className="mb-4 text-2xl font-semibold">Dataset Scorecards</h2>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-3">Dataset</th>
                  <th className="py-3">Owner</th>
                  <th className="py-3">Steward</th>
                  <th className="py-3">Certification</th>
                  <th className="py-3">Status</th>
                  <th className="py-3 text-right">Score</th>
                </tr>
              </thead>
              <tbody>
                {scorecards.map((dataset) => (
                  <tr
                    key={dataset.id}
                    className="border-b hover:bg-gray-50"
                  >
                    <td className="py-3">
                      <Link
                        href={`/datasets/${dataset.id}`}
                        className="font-semibold"
                      >
                        {dataset.schema_name}.{dataset.name}
                      </Link>
                      <div className="mt-1 text-xs text-gray-500">
                        {dataset.domain || "No domain"} · {dataset.tags || "No tags"}
                      </div>
                    </td>
                    <td className="py-3">{dataset.owner || "Unassigned"}</td>
                    <td className="py-3">{dataset.steward || "Unassigned"}</td>
                    <td className="py-3">{dataset.certification || "DRAFT"}</td>
                    <td className="py-3">{dataset.governance_status || "UNKNOWN"}</td>
                    <td className="py-3 text-right font-semibold">
                      {dataset.governance_score || 0}/100
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {scorecards.length === 0 && (
            <div className="py-8 text-gray-500">
              No datasets available for governance scoring yet.
            </div>
          )}
        </section>

        <div className="space-y-4">
          <Link
            href="/glossary"
            className="block rounded-xl bg-white p-6 shadow hover:bg-gray-50"
          >
            <h2 className="text-lg font-semibold">Business Glossary &rarr;</h2>
            <p className="mt-1 text-sm text-gray-500">
              Business definitions connected to the technical catalog at the
              dataset and column level.
            </p>
          </Link>

          <Link
            href="/processes"
            className="block rounded-xl bg-white p-6 shadow hover:bg-gray-50"
          >
            <h2 className="text-lg font-semibold">Process Repository &rarr;</h2>
            <p className="mt-1 text-sm text-gray-500">
              The end-to-end business activities each dataset supports,
              independent of team or domain.
            </p>
          </Link>

          <Link
            href="/reference-data"
            className="block rounded-xl bg-white p-6 shadow hover:bg-gray-50"
          >
            <h2 className="text-lg font-semibold">Reference Data &rarr;</h2>
            <p className="mt-1 text-sm text-gray-500">
              The controlled vocabularies and lookup tables other datasets
              point into.
            </p>
          </Link>
        </div>
      </div>
    </main>
  );
}
