import { stewardshipGaps } from "./stewardshipGaps";
import type { Dataset } from "../types/metadata";

// Minimal valid Dataset - only the fields stewardshipGaps actually
// reads are varied per test; everything else is filler to satisfy
// the type.
function makeDataset(overrides: Partial<Dataset> = {}): Dataset {
  return {
    id: "d1",
    source_id: "s1",
    name: "widgets",
    schema_name: "public",
    owner: "team-a",
    steward: "jane@datafe.io",
    domain: "commerce",
    description: "Widget catalog",
    governance_score: 90,
    ...overrides,
  };
}

describe("stewardshipGaps", () => {
  it("returns no gaps when everything is present and score is healthy", () => {
    expect(stewardshipGaps(makeDataset())).toEqual([]);
  });

  it("flags a missing owner", () => {
    expect(stewardshipGaps(makeDataset({ owner: "" }))).toContain("no owner");
    expect(stewardshipGaps(makeDataset({ owner: undefined }))).toContain("no owner");
  });

  it("flags a missing steward", () => {
    expect(stewardshipGaps(makeDataset({ steward: "" }))).toContain("no steward");
  });

  it("flags a missing domain", () => {
    expect(stewardshipGaps(makeDataset({ domain: "  " }))).toContain("no domain");
  });

  it("flags a missing description", () => {
    expect(stewardshipGaps(makeDataset({ description: "" }))).toContain("no description");
  });

  it("flags a governance score below 60 with the exact score in the message", () => {
    const gaps = stewardshipGaps(makeDataset({ governance_score: 42 }));
    expect(gaps).toContain("score 42");
  });

  it("does not flag a governance score at exactly the 60 boundary", () => {
    const gaps = stewardshipGaps(makeDataset({ governance_score: 60 }));
    expect(gaps.some((g) => g.startsWith("score"))).toBe(false);
  });

  it("treats a missing governance_score as healthy (defaults to 100)", () => {
    const gaps = stewardshipGaps(makeDataset({ governance_score: undefined }));
    expect(gaps.some((g) => g.startsWith("score"))).toBe(false);
  });

  it("accumulates multiple simultaneous gaps", () => {
    const gaps = stewardshipGaps(
      makeDataset({ owner: "", steward: "", domain: "", description: "", governance_score: 10 })
    );
    expect(gaps).toEqual(
      expect.arrayContaining(["no owner", "no steward", "no domain", "no description", "score 10"])
    );
    expect(gaps).toHaveLength(5);
  });
});
