"use client";

import { useState } from "react";

import { useStoryRecorder } from "../contexts/StoryRecorderContext";

/**
 * Floating "stitch your own story" recorder, mounted once in the root
 * layout (inside StoryRecorderProvider) so it persists across every
 * client-side navigation while recording - the whole point is that
 * someone browses the *actual* product, clicking "+ Add this view" at
 * whatever page tells the next part of the story, rather than filling
 * out a form describing pages they aren't looking at. Renders nothing
 * unless a recording is in progress (started from TourPickerModal's
 * "Record a new story").
 */
export default function StoryRecorderWidget() {
  const {
    isRecording,
    draftSteps,
    capturing,
    captureStep,
    removeStep,
    moveStep,
    discardRecording,
    saving,
    saveError,
    saveRecording,
  } = useStoryRecorder();

  const [addOpen, setAddOpen] = useState(false);
  const [stepTitle, setStepTitle] = useState("");
  const [stepNarrative, setStepNarrative] = useState("");

  const [reviewOpen, setReviewOpen] = useState(false);
  const [storyTitle, setStoryTitle] = useState("");
  const [storyProblem, setStoryProblem] = useState("");
  const [storySummary, setStorySummary] = useState("");

  if (!isRecording) return null;

  async function submitStep() {
    const title = stepTitle.trim();
    const narrative = stepNarrative.trim();
    if (!title || !narrative) return;

    await captureStep(title, narrative);
    setStepTitle("");
    setStepNarrative("");
    setAddOpen(false);
  }

  function handleDiscard() {
    if (draftSteps.length > 0 && !window.confirm(
      `Discard this story and its ${draftSteps.length} captured step${draftSteps.length === 1 ? "" : "s"}?`
    )) {
      return;
    }
    setAddOpen(false);
    setReviewOpen(false);
    discardRecording();
  }

  async function handleSave() {
    const title = storyTitle.trim();
    if (!title) return;

    const ok = await saveRecording(title, storyProblem.trim(), storySummary.trim());
    if (ok) {
      setReviewOpen(false);
      setStoryTitle("");
      setStoryProblem("");
      setStorySummary("");
    }
  }

  return (
    <>
      <div className="fixed bottom-4 left-4 z-50 w-full max-w-sm rounded-2xl border border-gray-200 bg-white shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-2.5">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-gray-400">Recording a story</div>
            <div className="text-sm font-semibold">
              {draftSteps.length} step{draftSteps.length === 1 ? "" : "s"} captured
            </div>
          </div>
          <button
            onClick={handleDiscard}
            className="shrink-0 rounded-full px-2 py-1 text-xs text-gray-400 hover:bg-gray-100 hover:text-gray-700"
          >
            Discard
          </button>
        </div>

        <div className="px-4 py-3">
          {!addOpen ? (
            <p className="mb-3 text-xs leading-relaxed text-gray-500">
              Browse to whatever page tells the next part of this story, then capture it here.
            </p>
          ) : (
            <div className="mb-3 space-y-2">
              <input
                type="text"
                value={stepTitle}
                onChange={(event) => setStepTitle(event.target.value)}
                placeholder={'Step title (e.g. "The authoritative table")'}
                className="w-full rounded-lg border px-2.5 py-1.5 text-sm"
                autoFocus
              />
              <textarea
                value={stepNarrative}
                onChange={(event) => setStepNarrative(event.target.value)}
                placeholder="What should the viewer notice on this page?"
                rows={3}
                className="w-full rounded-lg border px-2.5 py-1.5 text-sm"
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setAddOpen(false)}
                  className="rounded-lg px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100"
                >
                  Cancel
                </button>
                <button
                  onClick={submitStep}
                  disabled={capturing || !stepTitle.trim() || !stepNarrative.trim()}
                  className="rounded-lg bg-black px-3 py-1.5 text-xs text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  {capturing ? "Capturing..." : "Add this view"}
                </button>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between gap-2">
            {!addOpen && (
              <button
                onClick={() => setAddOpen(true)}
                className="rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-gray-50"
              >
                + Add this view
              </button>
            )}
            <button
              onClick={() => setReviewOpen(true)}
              disabled={draftSteps.length === 0}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                addOpen ? "" : "ml-auto"
              } bg-black text-white hover:bg-gray-800 disabled:opacity-40`}
            >
              Review &amp; save
            </button>
          </div>
        </div>
      </div>

      {reviewOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4">
          <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl bg-white shadow-2xl">
            <div className="border-b px-5 py-4">
              <h2 className="text-lg font-semibold">Save this story</h2>
              <p className="mt-1 text-sm text-gray-500">
                Give it a title so it shows up in the guided-tour picker for anyone else in your org.
              </p>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Title</label>
                <input
                  type="text"
                  value={storyTitle}
                  onChange={(event) => setStoryTitle(event.target.value)}
                  placeholder="e.g. Onboarding a new analyst"
                  className="w-full rounded-lg border px-2.5 py-1.5 text-sm"
                  autoFocus
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">
                  Problem statement <span className="font-normal text-gray-400">(optional)</span>
                </label>
                <textarea
                  value={storyProblem}
                  onChange={(event) => setStoryProblem(event.target.value)}
                  rows={2}
                  className="w-full rounded-lg border px-2.5 py-1.5 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">
                  Resolution summary <span className="font-normal text-gray-400">(optional)</span>
                </label>
                <textarea
                  value={storySummary}
                  onChange={(event) => setStorySummary(event.target.value)}
                  rows={2}
                  className="w-full rounded-lg border px-2.5 py-1.5 text-sm"
                />
              </div>

              <div className="border-t pt-3">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Steps ({draftSteps.length})
                </div>
                <div className="space-y-1.5">
                  {draftSteps.map((step, index) => (
                    <div
                      key={step.draftId}
                      className="flex items-start justify-between gap-2 rounded-lg border px-2.5 py-2 text-sm"
                    >
                      <div className="min-w-0">
                        <div className="font-medium text-gray-800">{step.title}</div>
                        <p className="mt-0.5 truncate text-xs text-gray-500">{step.narrative}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          onClick={() => moveStep(step.draftId, -1)}
                          disabled={index === 0}
                          aria-label="Move step up"
                          className="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-gray-100 disabled:opacity-30"
                        >
                          ↑
                        </button>
                        <button
                          onClick={() => moveStep(step.draftId, 1)}
                          disabled={index === draftSteps.length - 1}
                          aria-label="Move step down"
                          className="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-gray-100 disabled:opacity-30"
                        >
                          ↓
                        </button>
                        <button
                          onClick={() => removeStep(step.draftId)}
                          aria-label="Remove step"
                          className="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-gray-100"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {saveError && (
                <p className="rounded-lg bg-red-50 px-2.5 py-2 text-xs text-red-700">{saveError}</p>
              )}
            </div>

            <div className="flex items-center justify-between gap-2 border-t px-5 py-4">
              <button
                onClick={() => setReviewOpen(false)}
                className="rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-gray-100"
              >
                Back to recording
              </button>
              <div className="flex gap-2">
                <button
                  onClick={handleDiscard}
                  className="rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-gray-100"
                >
                  Discard story
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !storyTitle.trim() || draftSteps.length === 0}
                  className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Save story"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
