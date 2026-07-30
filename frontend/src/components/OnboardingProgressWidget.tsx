"use client";

import type { OnboardingProgress } from "../types/metadata";

type Props = {
  progress: OnboardingProgress | null;
};

export default function OnboardingProgressWidget({ progress }: Props) {
  if (!progress) return null;

  const isComplete = progress.completed_count === progress.total_count;

  return (
    <div className="rounded-xl border bg-white p-4 shadow">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-semibold text-gray-700">Your onboarding progress</div>
        <span className="text-xs text-gray-500">
          {progress.completed_count}/{progress.total_count}
        </span>
      </div>

      <div className="mb-3 h-2 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className="h-full rounded-full bg-black transition-all"
          style={{ width: `${progress.percent_complete}%` }}
        />
      </div>

      {isComplete && progress.ramp_days !== null && (
        <div className="mb-3 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700">
          Fully ramped on the ecosystem in {progress.ramp_days} day{progress.ramp_days === 1 ? "" : "s"} - this is the
          real, measured number behind the &ldquo;10 days instead of 3 months&rdquo; goal, not an estimate.
        </div>
      )}

      <ul className="space-y-1.5">
        {progress.milestones.map((milestone) => (
          <li key={milestone.key} className="flex items-center gap-2 text-xs">
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] ${
                milestone.completed ? "bg-black text-white" : "border border-gray-300 text-transparent"
              }`}
            >
              ✓
            </span>
            <span className={milestone.completed ? "text-gray-700" : "text-gray-400"}>{milestone.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
