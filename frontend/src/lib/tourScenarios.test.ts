import { findScenario, storyToScenario, TOUR_SCENARIOS } from "./tourScenarios";
import type { StoryResponse } from "../types/metadata";

describe("findScenario", () => {
  it("finds a built-in scenario by id", () => {
    const scenario = findScenario("discovery-bottleneck");
    expect(scenario).toBeDefined();
    expect(scenario?.title).toBe(TOUR_SCENARIOS[0].title);
  });

  it("returns undefined for an unknown or null id (e.g. a custom story's id)", () => {
    expect(findScenario(null)).toBeUndefined();
    expect(findScenario("some-uuid-that-is-a-custom-story")).toBeUndefined();
  });
});

describe("storyToScenario", () => {
  const STORY: StoryResponse = {
    id: "story-1",
    title: "Onboarding a new analyst",
    problem: "New hires don't know where to start.",
    solution_summary: "A guided lap around the parts that matter.",
    created_by_email: "steward@example.com",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    steps: [
      {
        id: "step-1",
        order_index: 0,
        title: "Search first",
        narrative: "Start with the catalog search.",
        path: "/",
        dataset_schema_name: null,
        dataset_table_name: null,
        tab: null,
        query_params: { q: "customer" },
      },
      {
        id: "step-2",
        order_index: 1,
        title: "The authoritative table",
        narrative: "This is the one to trust.",
        path: "/datasets/[id]",
        dataset_schema_name: "public",
        dataset_table_name: "customers",
        tab: "business",
        query_params: null,
      },
    ],
  };

  it("converts a Story into the exact TourScenario shape, marked isCustom", () => {
    const scenario = storyToScenario(STORY);

    expect(scenario.id).toBe("story-1");
    expect(scenario.title).toBe("Onboarding a new analyst");
    expect(scenario.problem).toBe("New hires don't know where to start.");
    expect(scenario.solutionSummary).toBe("A guided lap around the parts that matter.");
    expect(scenario.isCustom).toBe(true);
    expect(scenario.steps).toHaveLength(2);
  });

  it("only builds a target.dataset when both schema and table name are present", () => {
    const scenario = storyToScenario(STORY);

    expect(scenario.steps[0].target.dataset).toBeUndefined();
    expect(scenario.steps[0].target.query).toEqual({ q: "customer" });

    expect(scenario.steps[1].target.dataset).toEqual({ schemaName: "public", tableName: "customers" });
    expect(scenario.steps[1].target.tab).toBe("business");
  });

  it("defaults problem/solutionSummary to empty strings when the story omitted them", () => {
    const bare: StoryResponse = { ...STORY, problem: null, solution_summary: null };
    const scenario = storyToScenario(bare);

    expect(scenario.problem).toBe("");
    expect(scenario.solutionSummary).toBe("");
  });
});
