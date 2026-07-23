"use client";

import { useEffect, useState } from "react";

import api from "../services/api";
import type { MaturityLevel, MaturityOverview } from "../types/metadata";

const LEVEL_STYLES: Record<MaturityLevel, string> = {
  NOT_STARTED: "bg-gray-100 text-gray-600",
  AD_HOC: "bg-red-100 text-red-700",
  REACTIVE: "bg-orange-100 text-orange-700",
  MANAGED: "bg-blue-100 text-blue-700",
  TRUSTED: "bg-green-100 text-green-700",
};

const LEVEL_LABELS: Record<MaturityLevel, string> = {
  NOT_STARTED: "Not Started",
  AD_HOC: "Ad Hoc",
  REACTIVE: "Reactive",
  MANAGED: "Managed",
  TRUSTED: "Trusted",
};

function CoverageBar({ label, pct }: { label: string; pct: number }) {
  return (
    <div>
      <div className="flex items-center justify-between text-sm mb-1">
        <span className="text-gray-500">{label}</span>
        <span className="font-semibold">{pct}%</span>
      </div>
      <div className="w-full h-2 rounded-full bg-gray-100">
        <div
          className={`h-2 rounded-full ${
            pct >= 75 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function MaturityPanel() {
  const [maturity, setMaturity] = useState<MaturityOverview | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    async function fetchMaturity() {
      try {
        setErrorMessage(null);
        const response = await api.get<MaturityOverview>("/api/maturity");
        setMaturity(response.data);
      } catch (error) {
        console.error(error);
        setErrorMessage("Unable to load governance maturity right now.");
      }
    }

    fetchMaturity();
  }, []);

  if (errorMessage) {
    return (
      <div className="rounded-xl bg-white p-6 shadow mb-8 text-red-600">{errorMessage}</div>
    );
  }

  if (!maturity) {
    return (
      <div className="rounded-xl bg-white p-6 shadow mb-8 text-gray-500">
        Loading governance maturity...
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-white p-6 shadow mb-8">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_1fr_320px]">
        <div className="flex flex-col items-start justify-center">
          <div className="text-sm text-gray-500">Governance Maturity</div>
          <div className="text-5xl font-bold mt-1">{maturity.overall_score}</div>
          <span
            className={`mt-3 text-sm px-3 py-1 rounded-full font-medium ${LEVEL_STYLES[maturity.level]}`}
          >
            {LEVEL_LABELS[maturity.level]}
          </span>
          <div className="text-xs text-gray-500 mt-2">
            Based on {maturity.total_datasets} dataset{maturity.total_datasets === 1 ? "" : "s"}
          </div>
        </div>

        <div className="space-y-4">
          <CoverageBar label="Datasets with a real steward" pct={maturity.coverage.pct_with_steward} />
          <CoverageBar label="Datasets certified" pct={maturity.coverage.pct_certified} />
          <CoverageBar
            label="Datasets under an active contract"
            pct={maturity.coverage.pct_with_active_contract}
          />
          <CoverageBar
            label="PII datasets with a documented purpose"
            pct={maturity.coverage.pct_pii_with_documented_purpose}
          />
        </div>

        <div>
          <div className="text-sm font-semibold text-gray-700 mb-2">Recommended Next Steps</div>
          <ul className="space-y-2">
            {maturity.recommended_next_steps.map((step, index) => (
              <li key={index} className="text-sm text-gray-600 flex gap-2">
                <span className="text-gray-400">{index + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
