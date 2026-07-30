"use client";

import { useTour } from "../contexts/TourContext";

type TourPickerModalProps = {
  open: boolean;
  onClose: () => void;
  /**
   * Bulk-seeds the full demo estate in one shot and reloads - only
   * meaningful (and only passed) before any demo data exists yet. If
   * omitted, the "explore on my own" button just closes the modal -
   * used when reopening the picker on an org that already has demo
   * data, guided-tour-built or bulk-seeded, since re-running the bulk
   * seed at that point would just error.
   */
  onExploreOnMyOwn?: () => void;
  exploring?: boolean;
};

/**
 * Offers a guided walkthrough of one of the two problem -> process ->
 * solution scenarios, or a one-shot full seed to explore freely.
 * Picking a scenario does NOT pre-load any data - each tour step
 * creates just what it needs, live, as the stepper reaches it (see
 * TourContext's ensureStepData / backend guided_tour_service.py) -
 * so the catalog visibly comes alive while the story is being told,
 * rather than existing fully formed before the tour starts.
 */
export default function TourPickerModal({ open, onClose, onExploreOnMyOwn, exploring }: TourPickerModalProps) {
  const { scenarios, startTour } = useTour();

  if (!open) return null;

  async function pick(scenarioId: string) {
    onClose();
    await startTour(scenarioId);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="text-lg font-semibold">See it as a guided tour</h2>
        <p className="mt-1 text-sm text-gray-500">
          Pick one of two real problem-to-solution stories - the catalog builds itself live, one
          step at a time, as you walk through the actual product - or load the full estate at once
          to explore on your own.
        </p>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {scenarios.map((scenario) => (
            <button
              key={scenario.id}
              onClick={() => pick(scenario.id)}
              disabled={exploring}
              className="flex flex-col rounded-xl border border-gray-200 p-4 text-left hover:border-black hover:shadow-sm disabled:opacity-50"
            >
              <div className="text-sm font-semibold">{scenario.title}</div>
              <p className="mt-1.5 text-xs leading-relaxed text-gray-500">{scenario.problem}</p>
              <div className="mt-3 text-xs font-medium text-gray-700">
                {scenario.steps.length}-step tour →
              </div>
            </button>
          ))}
        </div>

        <div className="mt-5 flex justify-end">
          <button
            onClick={onExploreOnMyOwn ?? onClose}
            disabled={exploring}
            className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 disabled:opacity-50"
          >
            {onExploreOnMyOwn
              ? (exploring ? "Loading the full estate..." : "Just load everything and explore on my own")
              : "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
