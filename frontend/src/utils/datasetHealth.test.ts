import { getOverallHealth } from "./datasetHealth";
import type { Dataset } from "../types/metadata";

// Minimal valid Dataset - only the fields getOverallHealth actually
// reads are varied per test; everything else is filler to satisfy
// the type.
function makeDataset(overrides: Partial<Dataset> = {}): Dataset {
  return {
    id: "d1",
    source_id: "s1",
    name: "widgets",
    schema_name: "public",
    owner: "team-a",
    ...overrides,
  };
}

describe("getOverallHealth", () => {
  it("is HEALTHY when every status field is clean", () => {
    const result = getOverallHealth(makeDataset({
      governance_status: "HEALTHY",
      operational_status: "HEALTHY",
      contract_status: "COMPLIANT",
      freshness_status: "FRESH",
    }));

    expect(result.level).toBe("HEALTHY");
    expect(result.reasons).toEqual([]);
  });

  it("is HEALTHY when the status fields are simply absent (e.g. never scanned)", () => {
    const result = getOverallHealth(makeDataset());

    expect(result.level).toBe("HEALTHY");
    expect(result.reasons).toEqual([]);
  });

  it("flags a non-HEALTHY, non-CRITICAL governance status as NEEDS_ATTENTION", () => {
    const result = getOverallHealth(makeDataset({ governance_status: "AT_RISK" }));

    expect(result.level).toBe("NEEDS_ATTENTION");
    expect(result.reasons).toContain("governance status is at_risk");
  });

  it("escalates CRITICAL governance status to CRITICAL overall", () => {
    const result = getOverallHealth(makeDataset({ governance_status: "CRITICAL" }));

    expect(result.level).toBe("CRITICAL");
    expect(result.reasons).toContain("governance status is critical");
  });

  it("escalates UNSTABLE operational status to CRITICAL", () => {
    const result = getOverallHealth(makeDataset({ operational_status: "UNSTABLE" }));

    expect(result.level).toBe("CRITICAL");
    expect(result.reasons).toContain("operationally unstable");
  });

  it("treats AT_RISK and DEGRADED operational status as NEEDS_ATTENTION, not CRITICAL", () => {
    expect(getOverallHealth(makeDataset({ operational_status: "AT_RISK" })).level).toBe(
      "NEEDS_ATTENTION"
    );
    expect(getOverallHealth(makeDataset({ operational_status: "DEGRADED" })).level).toBe(
      "NEEDS_ATTENTION"
    );
  });

  it("escalates a BREACHED contract to CRITICAL", () => {
    const result = getOverallHealth(makeDataset({ contract_status: "BREACHED" }));

    expect(result.level).toBe("CRITICAL");
    expect(result.reasons).toContain("data contract is breached");
  });

  it("treats PENDING_EVALUATION contract status as NEEDS_ATTENTION", () => {
    const result = getOverallHealth(makeDataset({ contract_status: "PENDING_EVALUATION" }));

    expect(result.level).toBe("NEEDS_ATTENTION");
  });

  it("never downgrades CRITICAL back to NEEDS_ATTENTION from a later check", () => {
    // governance_status is CRITICAL (sets CRITICAL first), then
    // freshness_status is STALE (would only ever request
    // NEEDS_ATTENTION) - overall must stay CRITICAL.
    const result = getOverallHealth(makeDataset({
      governance_status: "CRITICAL",
      freshness_status: "STALE",
    }));

    expect(result.level).toBe("CRITICAL");
    expect(result.reasons).toEqual(
      expect.arrayContaining(["governance status is critical", "data is stale"])
    );
  });

  it("accumulates multiple reasons rather than stopping at the first issue", () => {
    const result = getOverallHealth(makeDataset({
      governance_status: "AT_RISK",
      freshness_status: "AGING",
    }));

    expect(result.reasons).toHaveLength(2);
  });
});
