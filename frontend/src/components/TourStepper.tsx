"use client";

import { useTour } from "../contexts/TourContext";

/**
 * Floating widget for the active guided tour - rendered once in the
 * root layout (inside TourProvider) so it persists across every page
 * navigation a tour step causes, rather than being re-mounted per
 * page. Renders nothing when no tour is active.
 */
export default function TourStepper() {
  const {
    activeScenario,
    currentStep,
    stepIndex,
    totalSteps,
    isResolving,
    resolveError,
    next,
    back,
    exitTour,
  } = useTour();

  if (!activeScenario || !currentStep) {
    return null;
  }

  const isLastStep = stepIndex === totalSteps - 1;
  const isFirstStep = stepIndex === 0;

  return (
    <div className="fixed bottom-4 right-4 z-50 w-full max-w-sm rounded-2xl border border-gray-200 bg-white shadow-xl">
      <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-2.5">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-gray-400">Guided tour</div>
          <div className="truncate text-sm font-semibold" title={activeScenario.title}>
            {activeScenario.title}
          </div>
        </div>
        <button
          onClick={exitTour}
          aria-label="Exit tour"
          className="shrink-0 rounded-full px-2 py-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
        >
          ✕
        </button>
      </div>

      <div className="px-4 py-3">
        <div className="mb-1.5 flex items-center gap-1.5">
          {activeScenario.steps.map((step, i) => (
            <div
              key={step.id}
              className={`h-1.5 flex-1 rounded-full ${
                i <= stepIndex ? "bg-black" : "bg-gray-200"
              }`}
            />
          ))}
        </div>
        <div className="mb-2 text-xs text-gray-400">
          Step {stepIndex + 1} of {totalSteps}
        </div>

        <div className="mb-1 text-sm font-semibold">{currentStep.title}</div>
        <p className="text-sm leading-relaxed text-gray-600">{currentStep.narrative}</p>

        {resolveError && (
          <p className="mt-2 rounded-lg bg-amber-50 px-2.5 py-2 text-xs text-amber-800">
            {resolveError}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-gray-100 px-4 py-2.5">
        <button
          onClick={back}
          disabled={isFirstStep || isResolving}
          className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
        >
          Back
        </button>
        <button
          onClick={next}
          disabled={isResolving}
          className="rounded-lg bg-black px-3.5 py-1.5 text-sm text-white hover:bg-gray-800 disabled:opacity-60"
        >
          {isResolving ? "Loading..." : isLastStep ? "Finish tour" : "Next"}
        </button>
      </div>
    </div>
  );
}
