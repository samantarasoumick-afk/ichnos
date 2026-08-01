"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import api from "../services/api";
import { findScenario, storyToScenario, TOUR_SCENARIOS, TourScenario, TourStep } from "../lib/tourScenarios";
import type { StoryResponse, StorySummary } from "../types/metadata";

const STORAGE_KEY = "datafe_tour_state_v1";

type StoredTourState = {
  scenarioId: string;
  stepIndex: number;
  // Which lookup path resuming needs: a static scenario resolves
  // synchronously via findScenario(); a custom (recorded) story needs
  // an async GET /api/stories/{id} first - see the resume effect below.
  isCustom: boolean;
};

type DatasetIndex = Record<string, string>;

function datasetKey(schemaName: string, tableName: string) {
  return `${schemaName}::${tableName}`;
}

function readStoredState(): StoredTourState | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as StoredTourState;

    // Only static scenarios can be validated synchronously here - a
    // custom story's existence (and org ownership) can only be
    // confirmed by actually fetching it, which the resume effect does.
    if (!parsed.isCustom && !findScenario(parsed.scenarioId)) return null;

    return parsed;
  } catch {
    return null;
  }
}

function writeStoredState(state: StoredTourState | null) {
  if (typeof window === "undefined") return;

  if (state === null) {
    window.localStorage.removeItem(STORAGE_KEY);
  } else {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }
}

/**
 * Turns a story summary (all GET /api/stories returns - title/problem/
 * step_count, deliberately no step detail) into a placeholder
 * TourScenario whose `steps` array exists only so picker UI can read
 * `.steps.length` for an accurate "N-step tour" count without fetching
 * full step detail for every story just to list them. Real steps are
 * only fetched (via startTour -> GET /api/stories/{id}) once someone
 * actually starts playing it.
 */
function summaryToShellScenario(summary: StorySummary): TourScenario {
  return {
    id: summary.id,
    title: summary.title,
    problem: summary.problem ?? "",
    solutionSummary: summary.solution_summary ?? "",
    isCustom: true,
    steps: Array.from({ length: summary.step_count }, (_, i) => ({
      id: `shell-${i}`,
      title: "",
      narrative: "",
      target: { path: "" },
    })),
  };
}

/**
 * Builds the URL for a tour step, resolving `dataset: {schemaName,
 * tableName}` against the live dataset index (fetched from
 * GET /api/datasets - see resolveDatasetIndex below) rather than a
 * hardcoded ID, since seeded dataset IDs are generated fresh per
 * organization every time the demo is loaded.
 */
function buildStepUrl(step: TourStep, datasetIndex: DatasetIndex): string | null {
  const { path, dataset, tab, query } = step.target;

  const params = new URLSearchParams(query ?? {});

  let resolvedPath = path;

  if (dataset) {
    const id = datasetIndex[datasetKey(dataset.schemaName, dataset.tableName)];

    // Not found - most likely the demo data isn't loaded (or was
    // cleared) in this organization, or (for a custom story) this org
    // just doesn't have a same-named dataset. Caller should treat this
    // as "can't navigate to this step" rather than sending the user to
    // a broken /datasets/undefined URL.
    if (!id) return null;

    if (path === "/datasets/[id]") {
      resolvedPath = `/datasets/${id}`;
    } else if (path === "/lineage") {
      params.set("dataset", id);
    }
  }

  if (tab) {
    params.set("tab", tab);
  }

  const queryString = params.toString();
  return queryString ? `${resolvedPath}?${queryString}` : resolvedPath;
}

type TourContextValue = {
  scenarios: TourScenario[];
  activeScenario: TourScenario | null;
  stepIndex: number;
  currentStep: TourStep | null;
  totalSteps: number;
  isResolving: boolean;
  resolveError: string | null;
  startTour: (scenarioId: string) => Promise<void>;
  goToStep: (index: number) => void;
  next: () => void;
  back: () => void;
  exitTour: () => void;
  // Custom (recorded) stories only - refetches the list (e.g. right
  // after saving a new one) and removes one, respectively. No-ops
  // that quietly do nothing useful if pointed at a built-in scenario
  // id, since those don't exist server-side to delete.
  refreshStories: () => Promise<void>;
  deleteStory: (storyId: string) => Promise<void>;
};

const TourContext = createContext<TourContextValue | undefined>(undefined);

export function TourProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  // Resume an in-progress tour after a page reload/navigation - the
  // stepper should still be visible wherever the user currently is,
  // not force a jump back to whatever step it thinks they're on. Read
  // lazily from localStorage via the initializer (same pattern used
  // throughout this app - see DiscussionsPage's filters) rather than
  // in an effect, so there's no synchronous setState-in-effect and no
  // one-frame flash of "no tour active" on every page load.
  const [scenarioId, setScenarioId] = useState<string | null>(() => readStoredState()?.scenarioId ?? null);
  const [stepIndex, setStepIndex] = useState(() => readStoredState()?.stepIndex ?? 0);
  // The fully resolved scenario currently playing, static or custom -
  // for a static scenario this is available synchronously (see the
  // initializer below); a custom one starts null and is filled in by
  // the resume effect once its GET /api/stories/{id} fetch completes.
  const [activeScenarioState, setActiveScenarioState] = useState<TourScenario | null>(() => {
    const stored = readStoredState();
    if (!stored || stored.isCustom) return null;
    return findScenario(stored.scenarioId) ?? null;
  });
  const [customStories, setCustomStories] = useState<StorySummary[]>([]);
  const [datasetIndex, setDatasetIndex] = useState<DatasetIndex | null>(null);
  const [isResolving, setIsResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);

  const fetchCustomStories = useCallback(async () => {
    try {
      const response = await api.get<StorySummary[]>("/api/stories");
      setCustomStories(response.data);
    } catch {
      // A logged-out or freshly-registered org with no stories yet -
      // the picker just shows the two built-in scenarios in that case,
      // same as before this feature existed.
    }
  }, []);

  useEffect(() => {
    // Deferred a tick, same reasoning as every other one-time mount
    // effect in this app (see ecosystem/page.tsx's deep-link effect):
    // this is a one-off fetch of external data, not something React
    // should be synchronously re-rendering for mid-effect.
    queueMicrotask(() => {
      fetchCustomStories();
    });
  }, [fetchCustomStories]);

  // One-time resume of an in-progress *custom* story after a reload -
  // static scenarios are already resolved synchronously above, so this
  // only has work to do when the stored state points at a custom one.
  // Guarded the same way ecosystem/page.tsx's own ?sourceId= deep link
  // is: a ref rather than a dependency array, so it fires exactly once
  // per page load regardless of what re-renders afterward.
  const ranCustomResumeRef = useRef(false);
  useEffect(() => {
    if (ranCustomResumeRef.current) return;
    ranCustomResumeRef.current = true;

    const stored = readStoredState();
    if (!stored || !stored.isCustom) return;

    queueMicrotask(async () => {
      try {
        const response = await api.get<StoryResponse>(`/api/stories/${stored.scenarioId}`);
        setActiveScenarioState(storyToScenario(response.data));
      } catch {
        // Story was deleted, or belongs to a different org than
        // whoever's session this now is - just drop the stale resume
        // state instead of leaving the stepper stuck unresolved.
        setScenarioId(null);
        setStepIndex(0);
        writeStoredState(null);
      }
    });
  }, []);

  // force=true bypasses the cache - needed after ensureStepData() below
  // has just (possibly) created new datasets, since a memoized index
  // from an earlier step wouldn't know about them yet.
  const resolveDatasetIndex = useCallback(
    async (force = false): Promise<DatasetIndex> => {
      if (datasetIndex && !force) return datasetIndex;

      try {
        const response = await api.get<Array<{ id: string; schema_name: string; name: string }>>(
          "/api/datasets"
        );

        const index: DatasetIndex = {};
        for (const d of response.data) {
          index[datasetKey(d.schema_name, d.name)] = d.id;
        }

        setDatasetIndex(index);
        return index;
      } catch {
        setResolveError(
          "Couldn't load the catalog to resolve this tour's datasets - is demo data still loaded?"
        );
        return {};
      }
    },
    [datasetIndex]
  );

  // Idempotently creates every piece of data this step (and its
  // prerequisites) needs - see backend/app/services/guided_tour_service.py.
  // Safe to call every time a step is reached, including re-visiting
  // one via Back: each checkpoint no-ops if its data already exists.
  // Only meaningful for the two built-in scenarios, which is why
  // navigateToStep below skips calling this entirely for a custom story.
  const ensureStepData = useCallback(async (scenarioId: string, index: number): Promise<boolean> => {
    try {
      await api.post(`/api/demo/tour/${scenarioId}/step/${index}`);
      return true;
    } catch {
      setResolveError(
        "Couldn't create this step's data - if you're not an admin or steward, ask one to load " +
          "the guided tour, or try again."
      );
      return false;
    }
  }, []);

  const navigateToStep = useCallback(
    async (scenario: TourScenario, index: number) => {
      const step = scenario.steps[index];
      if (!step) return;

      setIsResolving(true);
      setResolveError(null);

      if (!scenario.isCustom) {
        const created = await ensureStepData(scenario.id, index);
        if (!created) {
          setIsResolving(false);
          return;
        }
      }

      const index_ = await resolveDatasetIndex(true);
      setIsResolving(false);
      const url = buildStepUrl(step, index_);

      if (url) {
        setResolveError(null);

        // Several steps (the catalog search step, the ask-question
        // step) can land on a route the user is *already* on - e.g.
        // starting a tour from the Demo Data panel on "/" itself. That
        // page's search/prefill state is seeded once from
        // window.location.search in a lazy useState initializer (the
        // same pattern used throughout this app to avoid a
        // useSearchParams()/Suspense requirement), which a same-route
        // router.push() would never re-run since the component stays
        // mounted. A hard navigation forces a real remount so the new
        // query string actually takes effect.
        const currentPathname =
          typeof window !== "undefined" ? window.location.pathname : null;
        const targetPathname = url.split("?")[0];

        if (currentPathname === targetPathname) {
          window.location.href = url;
        } else {
          router.push(url);
        }
      } else {
        setResolveError(
          scenario.isCustom
            ? "Couldn't find this step's dataset in your catalog - this story may reference data " +
                "that doesn't exist here."
            : "Couldn't find this step's dataset - if you've cleared the demo data, reload it to " +
                "continue the tour."
        );
      }
    },
    [ensureStepData, resolveDatasetIndex, router]
  );

  const startTour = useCallback(
    async (id: string) => {
      const staticScenario = findScenario(id);

      if (staticScenario) {
        setActiveScenarioState(staticScenario);
        setScenarioId(id);
        setStepIndex(0);
        writeStoredState({ scenarioId: id, stepIndex: 0, isCustom: false });
        await navigateToStep(staticScenario, 0);
        return;
      }

      // Not a built-in scenario - fetch it as a custom story. Full step
      // detail is only ever fetched here, at actual playback time, not
      // when just listing stories in the picker.
      setIsResolving(true);
      setResolveError(null);

      try {
        const response = await api.get<StoryResponse>(`/api/stories/${id}`);
        const scenario = storyToScenario(response.data);

        setActiveScenarioState(scenario);
        setScenarioId(id);
        setStepIndex(0);
        writeStoredState({ scenarioId: id, stepIndex: 0, isCustom: true });
        setIsResolving(false);

        await navigateToStep(scenario, 0);
      } catch {
        setIsResolving(false);
        setResolveError("Couldn't load this story - it may have been deleted.");
      }
    },
    [navigateToStep]
  );

  const goToStep = useCallback(
    (index: number) => {
      const scenario = activeScenarioState;
      if (!scenario || index < 0 || index >= scenario.steps.length) return;

      setStepIndex(index);
      writeStoredState({ scenarioId: scenario.id, stepIndex: index, isCustom: !!scenario.isCustom });
      navigateToStep(scenario, index);
    },
    [activeScenarioState, navigateToStep]
  );

  const next = useCallback(() => {
    const scenario = activeScenarioState;
    if (!scenario) return;

    if (stepIndex >= scenario.steps.length - 1) {
      // Last step - finishing the tour clears it rather than looping.
      setScenarioId(null);
      setActiveScenarioState(null);
      setStepIndex(0);
      writeStoredState(null);
      return;
    }

    goToStep(stepIndex + 1);
  }, [activeScenarioState, stepIndex, goToStep]);

  const back = useCallback(() => {
    goToStep(stepIndex - 1);
  }, [stepIndex, goToStep]);

  const exitTour = useCallback(() => {
    setScenarioId(null);
    setActiveScenarioState(null);
    setStepIndex(0);
    setResolveError(null);
    writeStoredState(null);
  }, []);

  const deleteStory = useCallback(
    async (storyId: string) => {
      try {
        await api.delete(`/api/stories/${storyId}`);
        setCustomStories((prev) => prev.filter((story) => story.id !== storyId));

        // Deleting the story currently being played (rare, but
        // possible from another tab) ends it cleanly instead of
        // leaving the stepper pointed at data that no longer exists.
        if (scenarioId === storyId) {
          exitTour();
        }
      } catch {
        // Swallowed deliberately - the picker's delete affordance is a
        // convenience; a failed delete just leaves the story in the
        // list, which is a safe (if unhelpful) fallback state.
      }
    },
    [scenarioId, exitTour]
  );

  const currentStep = activeScenarioState ? activeScenarioState.steps[stepIndex] ?? null : null;

  const scenarios: TourScenario[] = [
    ...TOUR_SCENARIOS,
    ...customStories.map(summaryToShellScenario),
  ];

  return (
    <TourContext.Provider
      value={{
        scenarios,
        activeScenario: activeScenarioState,
        stepIndex,
        currentStep,
        totalSteps: activeScenarioState?.steps.length ?? 0,
        isResolving,
        resolveError,
        startTour,
        goToStep,
        next,
        back,
        exitTour,
        refreshStories: fetchCustomStories,
        deleteStory,
      }}
    >
      {children}
    </TourContext.Provider>
  );
}

export function useTour() {
  const context = useContext(TourContext);

  if (context === undefined) {
    throw new Error("useTour must be used within a TourProvider");
  }

  return context;
}
