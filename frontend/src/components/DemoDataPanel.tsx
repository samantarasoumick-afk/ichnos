"use client";

import { useEffect, useState } from "react";

import api from "../services/api";

import type { DemoStatus } from "../types/metadata";

import TourPickerModal from "./TourPickerModal";

export default function DemoDataPanel() {

  const [status, setStatus] = useState<DemoStatus | null>(null);

  const [loading, setLoading] = useState(false);

  // Shown right after a successful seed, offering the guided tour
  // instead of dropping the person back on a plain reloaded catalog
  // page with no orientation - see TourPickerModal/TourContext.
  const [showPicker, setShowPicker] = useState(false);

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

      await api.post("/api/demo/seed");

      // No alert()/reload here - the picker modal is the next step,
      // and either path out of it (pick a tour, or "explore on my
      // own") is responsible for getting the catalog page's data
      // fresh, see handleDismissPicker below and TourContext's
      // same-route hard-navigation handling.
      setShowPicker(true);

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

  // "Just explore on my own" out of the picker still needs the
  // catalog page's already-fetched (now stale) dataset list refreshed
  // - a full reload is the simplest reliable way, same as the
  // original load/clear flows below.
  function dismissPickerAndRefresh() {
    setShowPicker(false);
    window.location.reload();
  }

  if (!status) {
    return null;
  }

  return (
    <>
      <div className="bg-white rounded-xl p-6 shadow mb-8 flex items-center justify-between gap-4 flex-wrap">

        <div>
          <h2 className="text-lg font-semibold">
            Demo Data
          </h2>

          <p className="text-sm text-gray-500 mt-1 max-w-2xl">
            {status.demo_data_loaded
              ? `${status.demo_source_count} demo source(s) loaded - two guided stories in one ` +
                "connected estate: front-office apps through a dbt warehouse to Tableau " +
                "reporting, plus a vendor product feed whose data quality problem reaches a " +
                "downstream report - lineage, data quality, contracts, risks & controls, " +
                "privacy fields, team roles, and search activity all connected."
              : "Load a full, connected sample estate to see every feature working " +
                "together before bringing your own data - front office apps, a " +
                "processing layer, and reporting, plus a vendor feed whose data quality " +
                "problem you can trace end to end, with column-level lineage, data " +
                "quality, contracts, a risk register, privacy fields, and a mixed-role " +
                "team roster all in motion."}
          </p>
        </div>

        <div className="shrink-0 flex items-center gap-2">
          {status.demo_data_loaded && (
            <button
              onClick={() => setShowPicker(true)}
              disabled={loading}
              className="border border-gray-200 text-gray-700 px-4 py-2 rounded-xl hover:bg-gray-50"
            >
              Guided tour
            </button>
          )}

          {status.demo_data_loaded ? (
            <button
              onClick={clearDemoData}
              disabled={loading}
              className="border border-red-200 text-red-700 px-4 py-2 rounded-xl hover:bg-red-50"
            >
              {loading ? "Clearing..." : "Clear Demo Data"}
            </button>
          ) : (
            <button
              onClick={loadDemoData}
              disabled={loading}
              className="bg-black text-white px-4 py-2 rounded-xl"
            >
              {loading ? "Loading..." : "Load Demo Data"}
            </button>
          )}
        </div>

      </div>

      <TourPickerModal
        open={showPicker}
        onClose={status.demo_data_loaded ? () => setShowPicker(false) : dismissPickerAndRefresh}
      />
    </>
  );
}
