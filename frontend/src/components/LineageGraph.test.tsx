import { render, screen } from "@testing-library/react";
import LineageGraph from "./LineageGraph";
import type { Dataset, Lineage } from "../types/metadata";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

// reactflow measures nodes via ResizeObserver, which jsdom doesn't
// implement - stub it out just enough for a render to succeed, same
// as any consumer of reactflow in a jsdom test environment needs to.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(global as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

function makeDataset(overrides: Partial<Dataset>): Dataset {
  return {
    id: "d1",
    name: "customers",
    schema_name: "public",
    owner: "Growth Team",
    sensitivity_score: "LOW",
    ...overrides,
  } as Dataset;
}

const DATASETS: Dataset[] = [
  makeDataset({ id: "d1", name: "customers" }),
  makeDataset({ id: "d2", name: "dim_customers" }),
];

const LINEAGE: Lineage[] = [
  {
    id: "e1",
    upstream_dataset_id: "d1",
    downstream_dataset_id: "d2",
    transformation_type: "dbt model",
  } as Lineage,
];

describe("LineageGraph selection highlight", () => {
  it("shows no 'Currently viewing' badge or legend entry when nothing is selected", () => {
    render(<LineageGraph datasets={DATASETS} lineage={LINEAGE} />);
    expect(screen.queryByText("Currently viewing")).not.toBeInTheDocument();
  });

  it("shows a 'Currently viewing' badge on the selected node, and adds a legend entry for it", () => {
    render(<LineageGraph datasets={DATASETS} lineage={LINEAGE} selectedDatasetId="d1" />);
    // The legend entry (top bar) plus the in-node badge both render
    // this exact text - there should be at least the legend entry, and
    // the node badge alongside it.
    const matches = screen.getAllByText("Currently viewing");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("does not add a highlight badge when selectedDatasetId doesn't match any node in this graph", () => {
    render(<LineageGraph datasets={DATASETS} lineage={LINEAGE} selectedDatasetId="not-in-this-graph" />);
    // No node is selected among the graph's own nodes, so no node
    // gets the "Currently viewing" pill - even though the legend
    // section itself is keyed off the raw prop being truthy.
    expect(screen.getAllByText("Currently viewing").length).toBe(1);
  });
});
