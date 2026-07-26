"use client";

import { useEffect, useState } from "react";

import api from "../services/api";

import type { DemoStatus } from "../types/metadata";

export default function DemoDataPanel() {

  const [status, setStatus] = useState<DemoStatus | null>(null);

  const [loading, setLoading] = useState(false);

  useEffect(() => {

    async function loadStatus() {
      try {
        const response = await api.get<DemoStatus>("/api/demo/status");
        setStatus(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    loadStatus();

  }, []);

  async function loadDemoData() {

    try {

      setLoading(true);

      const response = await api.post("/api/demo/seed");

      alert(
        `Demo data loaded: ${response.data.sources_created} source(s), ` +
          `${response.data.datasets_created} dataset(s) across front office, ` +
          `processing, and reporting - plus ${response.data.risks_created} risk(s), ` +
          `${response.data.controls_created} control(s), and ` +
          `${response.data.team_members_created} extra team member(s).`
      );

      window.location.reload();

    } catch (error: unknown) {

      console.error(error);

      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

      alert(detail || "Failed to load demo data");

    } finally {

      setLoading(false);
    }
  }

  async function clearDemoData() {

    if (
      !window.confirm(
        "This removes every demo source, dataset, lineage edge, contract, and " +
          "discussion the demo seeder created - anything you connected yourself is " +
          "left untouched. Continue?"
      )
    ) {
      return;
    }

    try {

      setLoading(true);

      const response = await api.post("/api/demo/clear");

      alert(
        `Demo data cleared: ${response.data.sources_removed} source(s), ` +
          `${response.data.datasets_removed} dataset(s) removed.`
      );

      window.location.reload();

    } catch (error: unknown) {

      console.error(error);

      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

      alert(detail || "Failed to clear demo data");

    } finally {

      setLoading(false);
    }
  }

  if (!status) {
    return null;
  }

  return (

    <div className="bg-white rounded-xl p-6 shadow mb-8 flex items-center justify-between gap-4 flex-wrap">

      <div>
        <h2 className="text-lg font-semibold">
          Demo Data
        </h2>

        <p className="text-sm text-gray-500 mt-1 max-w-2xl">
          {status.demo_data_loaded
            ? `${status.demo_source_count} demo source(s) loaded - three front-office ` +
              "applications feeding a dbt-modeled warehouse feeding Tableau reporting, " +
              "with lineage, data quality, contracts, risks & controls, privacy fields, " +
              "team roles, and search activity all connected."
            : "Load a full, connected sample estate to see every feature working " +
              "together before bringing your own data - front office apps, a " +
              "processing layer, and reporting, with column-level lineage, data " +
              "quality, contracts, a risk register, privacy fields, and a mixed-role " +
              "team roster all in motion."}
        </p>
      </div>

      {status.demo_data_loaded ? (
        <button
          onClick={clearDemoData}
          disabled={loading}
          className="shrink-0 border border-red-200 text-red-700 px-4 py-2 rounded-xl hover:bg-red-50"
        >
          {loading ? "Clearing..." : "Clear Demo Data"}
        </button>
      ) : (
        <button
          onClick={loadDemoData}
          disabled={loading}
          className="shrink-0 bg-black text-white px-4 py-2 rounded-xl"
        >
          {loading ? "Loading..." : "Load Demo Data"}
        </button>
      )}

    </div>
  );
}
