"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import api from "../services/api";
import { findScenario, TOUR_SCENARIOS, TourScenario, TourStep } from "../lib/tourScenarios";

const STORAGE_KEY = "datafe_tour_state_v1";

type StoredTourState = {
  scenarioId: string;
  stepIndex: number;
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
    if (!findScenario(parsed.scenarioId)) return null;

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
    // cleared) in this organization. Caller should treat this as
    // "can't navigate to this step" rather than sending the user to a
    // broken /datasets/undefined URL.
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
  const [datasetIndex, setDatasetIndex] = useState<DatasetIndex | null>(null);
  const [isResolving, setIsResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);

  const resolveDatasetIndex = useCallback(async (): Promise<DatasetIndex> => {
    if (datasetIndex) return datasetIndex;

    setIsResolving(true);
    setResolveError(null);

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
    } finally {
      setIsResolving(false);
    }
  }, [datasetIndex]);

  const navigateToStep = useCallback(
    async (scenario: TourScenario, index: number) => {
      const step = scenario.steps[index];
      if (!step) return;

      const index_ = await resolveDatasetIndex();
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
          "Couldn't find this step's dataset - if you've cleared the demo data, reload it to " +
            "continue the tour."
        );
      }
    },
    [resolveDatasetIndex, router]
  );

  const startTour = useCallback(
    async (id: string) => {
      const scenario = findScenario(id);
      if (!scenario) return;

      setScenarioId(id);
      setStepIndex(0);
      writeStoredState({ scenarioId: id, stepIndex: 0 });

      await navigateToStep(scenario, 0);
    },
    [navigateToStep]
  );

  const goToStep = useCallback(
    (index: number) => {
      const scenario = findScenario(scenarioId);
      if (!scenario || index < 0 || index >= scenario.steps.length) return;

      setStepIndex(index);
      writeStoredState({ scenarioId: scenario.id, stepIndex: index });
      navigateToStep(scenario, index);
    },
    [scenarioId, navigateToStep]
  );

  const next = useCallback(() => {
    const scenario = findScenario(scenarioId);
    if (!scenario) return;

    if (stepIndex >= scenario.steps.length - 1) {
      // Last step - finishing the tour clears it rather than looping.
      setScenarioId(null);
      setStepIndex(0);
      writeStoredState(null);
      return;
    }

    goToStep(stepIndex + 1);
  }, [scenarioId, stepIndex, goToStep]);

  const back = useCallback(() => {
    goToStep(stepIndex - 1);
  }, [stepIndex, goToStep]);

  const exitTour = useCallback(() => {
    setScenarioId(null);
    setStepIndex(0);
    setResolveError(null);
    writeStoredState(null);
  }, []);

  const activeScenario = findScenario(scenarioId) ?? null;
  const currentStep = activeScenario ? activeScenario.steps[stepIndex] ?? null : null;

  return (
    <TourContext.Provider
      value={{
        scenarios: TOUR_SCENARIOS,
        activeScenario,
        stepIndex,
        currentStep,
        totalSteps: activeScenario?.steps.length ?? 0,
        isResolving,
        resolveError,
        startTour,
        goToStep,
        next,
        back,
        exitTour,
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
