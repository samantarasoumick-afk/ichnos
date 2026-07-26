import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import DataQualityPage from "./page";
import api from "../../services/api";

jest.mock("../../components/TopNav", () => ({
  __esModule: true,
  default: () => <div data-testid="top-nav" />,
}));

jest.mock("../../hooks/useRequireAuth", () => ({
  useRequireAuth: () => ({
    user: { id: "u1", email: "steward@example.com", role: "steward" },
    loading: false,
  }),
}));

jest.mock("../../services/api", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedGet = api.get as jest.Mock;

const DATASETS = [
  {
    id: "d1",
    source_id: "s1",
    name: "customers",
    schema_name: "public",
    owner: "Growth Team",
    domain: "Growth",
  },
  {
    id: "d2",
    source_id: "s1",
    name: "orders",
    schema_name: "public",
    owner: "Growth Team",
    domain: "Growth",
  },
  {
    id: "d3",
    source_id: "s2",
    name: "fct_customer_orders",
    schema_name: "analytics",
    owner: "BI Team",
    domain: "BI",
  },
];

const DQ = [
  {
    id: "dq1",
    dataset_id: "d1",
    completeness: 95,
    uniqueness: 90,
    validity: 92,
    consistency: 88,
    freshness: 99,
    overall_score: 92,
  },
  {
    id: "dq2",
    dataset_id: "d3",
    completeness: 40,
    uniqueness: 45,
    validity: 30,
    consistency: 50,
    freshness: 20,
    overall_score: 35,
  },
];

function mockLoad() {
  mockedGet.mockImplementation((url: string) => {
    if (url === "/api/datasets") return Promise.resolve({ data: DATASETS });
    if (url === "/api/data-quality") return Promise.resolve({ data: DQ });
    if (url === "/api/data-quality/effective") return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`unexpected url ${url}`));
  });
}

describe("DataQualityPage", () => {
  beforeEach(() => {
    mockedGet.mockReset();
  });

  it("loads and renders all datasets by default", async () => {
    mockLoad();
    render(<DataQualityPage />);

    expect(await screen.findByText("public.customers")).toBeInTheDocument();
    expect(screen.getByText("public.orders")).toBeInTheDocument();
    expect(screen.getByText("analytics.fct_customer_orders")).toBeInTheDocument();
  });

  it("picking a schema suggestion filters the list down to that schema", async () => {
    mockLoad();
    render(<DataQualityPage />);
    await screen.findByText("public.customers");

    const input = screen.getByPlaceholderText("Search datasets...");
    fireEvent.change(input, { target: { value: "public" } });
    fireEvent.mouseDown(screen.getByText("public"));

    await waitFor(() =>
      expect(screen.queryByText("analytics.fct_customer_orders")).not.toBeInTheDocument()
    );
    expect(screen.getByText("public.customers")).toBeInTheDocument();
    expect(screen.getByText("public.orders")).toBeInTheDocument();
    expect(screen.getByText("Schema: public")).toBeInTheDocument();
  });

  it("clearing the schema filter chip restores the full list", async () => {
    mockLoad();
    render(<DataQualityPage />);
    await screen.findByText("public.customers");

    const input = screen.getByPlaceholderText("Search datasets...");
    fireEvent.change(input, { target: { value: "public" } });
    fireEvent.mouseDown(screen.getByText("public"));

    const chip = await screen.findByText("Schema: public");
    fireEvent.click(chip);

    await waitFor(() =>
      expect(screen.getByText("analytics.fct_customer_orders")).toBeInTheDocument()
    );
  });

  it("picking a dataset suggestion narrows the list to that one dataset", async () => {
    mockLoad();
    render(<DataQualityPage />);
    await screen.findByText("public.customers");

    const input = screen.getByPlaceholderText("Search datasets...");
    fireEvent.change(input, { target: { value: "fct_customer" } });
    fireEvent.mouseDown(screen.getByText("analytics.fct_customer_orders"));

    await waitFor(() => expect(screen.queryByText("public.customers")).not.toBeInTheDocument());
    expect(screen.getByText("analytics.fct_customer_orders")).toBeInTheDocument();
  });
});
