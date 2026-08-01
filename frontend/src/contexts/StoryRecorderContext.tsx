"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";

import api from "../services/api";
import { useTour } from "./TourContext";
import type { StoryStepCreate } from "../types/metadata";

const STORAGE_KEY = "datafe_story_draft_v1";

export type DraftStep = StoryStepCreate & {
  // Local-only identifier for React keys / removal - never sent to
  // the backend (StoryStepCreate has no id field; order_index is
  // derived server-side from array position, see app/api/stories.py).
  draftId: string;
};

type DraftState = {
  steps: DraftStep[];
};

function readDraft(): DraftState {
  if (typeof window === "undefined") return { steps: [] };

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { steps: [] };
    const parsed = JSON.parse(raw) as DraftState;
    return { steps: Array.isArray(parsed.steps) ? parsed.steps : [] };
  } catch {
    return { steps: [] };
  }
}

function writeDraft(state: DraftState | null) {
  if (typeof window === "undefined") return;

  if (state === null) {
    window.localStorage.removeItem(STORAGE_KEY);
  } else {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }
}

/**
 * Resolves the *current* page into a portable story step target -
 * the recording-time counterpart to TourContext's buildStepUrl, which
 * resolves a step target back into a URL at playback time. A dataset
 * detail page or the lineage page (both addressed by raw dataset ID in
 * their URL) get resolved to a portable {schemaName, tableName} pair
 * via a single dataset lookup, exactly like the two hand-written
 * scenarios in tourScenarios.ts already reference their datasets -
 * that's what lets a recorded story replay correctly in a *different*
 * org's catalog, not just the one it was recorded in.
 */
async function captureCurrentView(): Promise<{
  path: string;
  dataset?: { schema_name: string; table_name: string };
  tab?: string;
  query?: Record<string, string>;
}> {
  const pathname = window.location.pathname;
  const params = new URLSearchParams(window.location.search);

  const tab = params.get("tab") ?? undefined;
  params.delete("tab");

  const datasetDetailMatch = pathname.match(/^\/datasets\/([^/]+)$/);
  const lineageDatasetId = pathname === "/lineage" ? params.get("dataset") : null;
  if (lineageDatasetId) params.delete("dataset");

  const datasetId = datasetDetailMatch?.[1] ?? lineageDatasetId ?? null;

  let path = pathname;
  let dataset: { schema_name: string; table_name: string } | undefined;

  if (datasetId) {
    try {
      const response = await api.get<{ schema_name: string; name: string }>(`/api/datasets/${datasetId}`);
      dataset = { schema_name: response.data.schema_name, table_name: response.data.name };
      path = datasetDetailMatch ? "/datasets/[id]" : "/lineage";
    } catch {
      // Couldn't resolve the dataset (deleted mid-recording, etc.) -
      // fall back to capturing the raw path with no portable dataset
      // reference rather than failing the whole capture.
    }
  }

  const query: Record<string, string> = {};
  params.forEach((value, key) => {
    query[key] = value;
  });

  return {
    path,
    dataset,
    tab,
    query: Object.keys(query).length > 0 ? query : undefined,
  };
}

type StoryRecorderContextValue = {
  isRecording: boolean;
  draftSteps: DraftStep[];
  startRecording: () => void;
  capturing: boolean;
  captureStep: (title: string, narrative: string) => Promise<void>;
  removeStep: (draftId: string) => void;
  moveStep: (draftId: string, direction: -1 | 1) => void;
  discardRecording: () => void;
  saving: boolean;
  saveError: string | null;
  saveRecording: (title: string, problem: string, solutionSummary: string) => Promise<boolean>;
};

const StoryRecorderContext = createContext<StoryRecorderContextValue | undefined>(undefined);

export function StoryRecorderProvider({ children }: { children: React.ReactNode }) {
  const { refreshStories } = useTour();

  const [isRecording, setIsRecording] = useState(() => readDraft().steps.length > 0);
  const [draftSteps, setDraftSteps] = useState<DraftStep[]>(() => readDraft().steps);
  const [capturing, setCapturing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const startRecording = useCallback(() => {
    setIsRecording(true);
    setSaveError(null);
  }, []);

  const captureStep = useCallback(async (title: string, narrative: string) => {
    setCapturing(true);
    try {
      const target = await captureCurrentView();

      const step: DraftStep = {
        draftId: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        title,
        narrative,
        path: target.path,
        dataset: target.dataset
          ? { schema_name: target.dataset.schema_name, table_name: target.dataset.table_name }
          : undefined,
        tab: target.tab,
        query: target.query,
      };

      setDraftSteps((prev) => {
        const next = [...prev, step];
        writeDraft({ steps: next });
        return next;
      });
    } finally {
      setCapturing(false);
    }
  }, []);

  const removeStep = useCallback((draftId: string) => {
    setDraftSteps((prev) => {
      const next = prev.filter((step) => step.draftId !== draftId);
      writeDraft({ steps: next });
      return next;
    });
  }, []);

  const moveStep = useCallback((draftId: string, direction: -1 | 1) => {
    setDraftSteps((prev) => {
      const index = prev.findIndex((step) => step.draftId === draftId);
      const targetIndex = index + direction;
      if (index < 0 || targetIndex < 0 || targetIndex >= prev.length) return prev;

      const next = [...prev];
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      writeDraft({ steps: next });
      return next;
    });
  }, []);

  const discardRecording = useCallback(() => {
    setIsRecording(false);
    setDraftSteps([]);
    setSaveError(null);
    writeDraft(null);
  }, []);

  const saveRecording = useCallback(
    async (title: string, problem: string, solutionSummary: string): Promise<boolean> => {
      if (draftSteps.length === 0) {
        setSaveError("Add at least one step before saving.");
        return false;
      }

      setSaving(true);
      setSaveError(null);

      try {
        await api.post("/api/stories", {
          title,
          problem: problem || undefined,
          solution_summary: solutionSummary || undefined,
          // draftId is a local-only React key, never part of the
          // StoryStepCreate shape the backend expects.
          steps: draftSteps.map((step): StoryStepCreate => ({
            title: step.title,
            narrative: step.narrative,
            path: step.path,
            dataset: step.dataset,
            tab: step.tab,
            query: step.query,
          })),
        });

        await refreshStories();

        setIsRecording(false);
        setDraftSteps([]);
        writeDraft(null);
        return true;
      } catch (error) {
        const detail =
          (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setSaveError(detail || "Couldn't save this story - try again.");
        return false;
      } finally {
        setSaving(false);
      }
    },
    [draftSteps, refreshStories]
  );

  return (
    <StoryRecorderContext.Provider
      value={{
        isRecording,
        draftSteps,
        startRecording,
        capturing,
        captureStep,
        removeStep,
        moveStep,
        discardRecording,
        saving,
        saveError,
        saveRecording,
      }}
    >
      {children}
    </StoryRecorderContext.Provider>
  );
}

export function useStoryRecorder() {
  const context = useContext(StoryRecorderContext);

  if (context === undefined) {
    throw new Error("useStoryRecorder must be used within a StoryRecorderProvider");
  }

  return context;
}
