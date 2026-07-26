import { useState } from "react";

import { fireEvent, render, screen } from "@testing-library/react";

import SchemaDatasetSearch from "./SchemaDatasetSearch";
import type { Dataset } from "../types/metadata";

function makeDataset(overrides: Partial<Dataset>): Dataset {
  return {
    id: overrides.id ?? "d1",
    source_id: "s1",
    name: overrides.name ?? "customers",
    schema_name: overrides.schema_name ?? "public",
    owner: "Growth Team",
    ...overrides,
  };
}

const DATASETS: Dataset[] = [
  makeDataset({ id: "d1", schema_name: "public", name: "customers", domain: "Growth" }),
  makeDataset({ id: "d2", schema_name: "public", name: "orders", domain: "Growth" }),
  makeDataset({ id: "d3", schema_name: "analytics", name: "fct_customer_orders", domain: "BI" }),
];

function Harness({ onPickSchema }: { onPickSchema: (schema: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <SchemaDatasetSearch
      datasets={DATASETS}
      value={value}
      onChange={setValue}
      onPickSchema={onPickSchema}
    />
  );
}

describe("SchemaDatasetSearch", () => {
  it("shows no suggestions before typing", () => {
    render(<Harness onPickSchema={jest.fn()} />);
    expect(screen.queryByText("Schema")).not.toBeInTheDocument();
  });

  it("suggests both a matching schema and matching datasets while typing", () => {
    render(<Harness onPickSchema={jest.fn()} />);
    const input = screen.getByPlaceholderText("Search schema or dataset...");

    fireEvent.change(input, { target: { value: "public" } });

    expect(screen.getByText("public")).toBeInTheDocument();
    expect(screen.getByText("2 datasets")).toBeInTheDocument();
    expect(screen.getByText("public.customers")).toBeInTheDocument();
    expect(screen.getByText("public.orders")).toBeInTheDocument();
    expect(screen.queryByText("analytics.fct_customer_orders")).not.toBeInTheDocument();
  });

  it("picking a schema suggestion calls onPickSchema and clears the text", () => {
    const onPickSchema = jest.fn();
    render(<Harness onPickSchema={onPickSchema} />);
    const input = screen.getByPlaceholderText("Search schema or dataset...") as HTMLInputElement;

    fireEvent.change(input, { target: { value: "analytics" } });
    fireEvent.mouseDown(screen.getByText("analytics"));

    expect(onPickSchema).toHaveBeenCalledWith("analytics");
    expect(input.value).toBe("");
  });

  it("picking a dataset suggestion sets the exact schema.name text", () => {
    const onPickSchema = jest.fn();
    render(<Harness onPickSchema={onPickSchema} />);
    const input = screen.getByPlaceholderText("Search schema or dataset...") as HTMLInputElement;

    fireEvent.change(input, { target: { value: "fct_customer" } });
    fireEvent.mouseDown(screen.getByText("analytics.fct_customer_orders"));

    expect(input.value).toBe("analytics.fct_customer_orders");
    expect(onPickSchema).not.toHaveBeenCalled();
  });

  it("supports arrow-key navigation and Enter to select", () => {
    const onPickSchema = jest.fn();
    render(<Harness onPickSchema={onPickSchema} />);
    const input = screen.getByPlaceholderText("Search schema or dataset...");

    fireEvent.change(input, { target: { value: "public" } });
    // Suggestions order: schema "public" first, then dataset matches.
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onPickSchema).toHaveBeenCalledWith("public");
  });

  it("finds no suggestions for a nonsense query", () => {
    render(<Harness onPickSchema={jest.fn()} />);
    const input = screen.getByPlaceholderText("Search schema or dataset...");

    fireEvent.change(input, { target: { value: "zzzznonexistent" } });

    expect(screen.queryByText("Schema")).not.toBeInTheDocument();
    expect(screen.queryByText("Dataset")).not.toBeInTheDocument();
  });
});
