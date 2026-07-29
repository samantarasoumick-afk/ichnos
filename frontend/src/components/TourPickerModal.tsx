"use client";

import { useTour } from "../contexts/TourContext";

type TourPickerModalProps = {
  open: boolean;
  onClose: () => void;
};

/**
 * Shown right after demo data loads (see DemoDataPanel) - offers a
 * guided walkthrough of one of the two problem -> process -> solution
 * scenarios instead of dropping the person on a reloaded catalog page
 * with no orientation. Can also be reopened later via the "Guided
 * tour" button DemoDataPanel shows once demo data is loaded.
 */
export default function TourPickerModal({ open, onClose }: TourPickerModalProps) {
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
          The demo estate tells two real problem-to-solution stories. Pick one to walk through it
          step by step across the actual product, or explore on your own.
        </p>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {scenarios.map((scenario) => (
            <button
              key={scenario.id}
              onClick={() => pick(scenario.id)}
              className="flex flex-col rounded-xl border border-gray-200 p-4 text-left hover:border-black hover:shadow-sm"
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
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:bg-gray-100">
            Just explore on my own
          </button>
        </div>
      </div>
    </div>
  );
}
