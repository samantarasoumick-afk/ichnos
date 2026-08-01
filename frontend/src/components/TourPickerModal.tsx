"use client";

import { useStoryRecorder } from "../contexts/StoryRecorderContext";
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
  const { scenarios, startTour, deleteStory } = useTour();
  const { startRecording } = useStoryRecorder();

  if (!open) return null;

  async function pick(scenarioId: string) {
    onClose();
    await startTour(scenarioId);
  }

  function record() {
    onClose();
    startRecording();
  }

  async function remove(event: React.MouseEvent, storyId: string, title: string) {
    event.stopPropagation();
    if (!window.confirm(`Delete the story "${title}"? This can't be undone.`)) return;
    await deleteStory(storyId);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="text-lg font-semibold">See it as a guided tour</h2>
        <p className="mt-1 text-sm text-gray-500">
          Pick one of two real problem-to-solution stories - the catalog builds itself live, one
          step at a time, as you walk through the actual product - load the full estate at once to
          explore on your own, or stitch together your own story from any pages you like.
        </p>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {scenarios.map((scenario) => (
            <button
              key={scenario.id}
              onClick={() => pick(scenario.id)}
              disabled={exploring}
              className="group relative flex flex-col rounded-xl border border-gray-200 p-4 text-left hover:border-black hover:shadow-sm disabled:opacity-50"
            >
              {scenario.isCustom && (
                <button
                  onClick={(event) => remove(event, scenario.id, scenario.title)}
                  aria-label={`Delete story "${scenario.title}"`}
                  className="absolute right-2 top-2 rounded-full px-1.5 py-0.5 text-xs text-gray-300 opacity-0 hover:bg-gray-100 hover:text-gray-600 group-hover:opacity-100"
                >
                  ✕
                </button>
              )}
              <div className="flex items-center gap-1.5">
                {scenario.isCustom && (
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[9px] font-medium uppercase text-gray-500">
                    Your team
                  </span>
                )}
                <div className="text-sm font-semibold">{scenario.title}</div>
              </div>
              {scenario.problem && (
                <p className="mt-1.5 text-xs leading-relaxed text-gray-500">{scenario.problem}</p>
              )}
              <div className="mt-3 text-xs font-medium text-gray-700">
                {scenario.steps.length}-step tour →
              </div>
            </button>
          ))}

          <button
            onClick={record}
            className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 p-4 text-center text-gray-500 hover:border-black hover:text-black"
          >
            <div className="text-sm font-semibold">+ Record a new story</div>
            <p className="mt-1.5 text-xs leading-relaxed">
              Walk through any pages yourself, narrate each one, and save it for your team.
            </p>
          </button>
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
