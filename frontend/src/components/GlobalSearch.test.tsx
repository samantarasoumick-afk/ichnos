import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import GlobalSearch from "./GlobalSearch";
import api from "../services/api";

const pushMock = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

jest.mock("../services/api", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedGet = api.get as jest.Mock;

function getSearchInput() {
  return screen.getByPlaceholderText(/Search everything/);
}

const MENTION_RESULTS = [
  { type: "dataset", id: "d1", label: "public.customers", subtitle: "public" },
  { type: "glossary_term", id: "g1", label: "Customer Lifetime Value", subtitle: "Glossary term" },
];

const RESULTS = [
  {
    type: "dataset",
    id: "d1",
    label: "public.customers",
    subtitle: "public",
    snippet: "Customer records",
    url: "/datasets/d1",
    score: 0.9,
  },
  {
    type: "risk",
    id: "r1",
    label: "Unmasked PII risk",
    subtitle: "Risk · PRIVACY · OPEN",
    snippet: "Exposure via reporting layer",
    url: "/risks",
    score: 0.5,
  },
];

const TIERED_RESULTS = [
  {
    type: "source",
    id: "s1",
    label: "Salesforce CRM",
    subtitle: "Source · postgresql · 2 datasets",
    snippet: "",
    url: "/ecosystem?sourceId=s1",
    score: 0.9,
  },
  {
    type: "dataset",
    id: "d1",
    label: "public.customers",
    subtitle: "public",
    snippet: "",
    url: "/datasets/d1",
    score: 0.8,
  },
  {
    type: "column",
    id: "c1",
    label: "email",
    subtitle: "Column · public.customers",
    snippet: "",
    url: "/datasets/d1?tab=columns&highlightColumn=c1",
    score: 0.7,
  },
];

describe("GlobalSearch", () => {
  beforeEach(() => {
    pushMock.mockClear();
    mockedGet.mockReset();
  });

  it("does not show a dropdown before anything is typed", () => {
    render(<GlobalSearch />);
    expect(screen.queryByText(/Searching/)).not.toBeInTheDocument();
  });

  it("debounces input and fetches /api/search, rendering typed results", async () => {
    mockedGet.mockResolvedValue({ data: { results: RESULTS } });

    render(<GlobalSearch />);
    const input = getSearchInput();

    fireEvent.change(input, { target: { value: "customers" } });

    // Nothing fired yet - still inside the debounce window.
    expect(mockedGet).not.toHaveBeenCalled();

    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
    expect(mockedGet).toHaveBeenCalledWith(
      "/api/search",
      expect.objectContaining({ params: { q: "customers", limit: 15 } })
    );

    expect(await screen.findByText("public.customers")).toBeInTheDocument();
    expect(screen.getByText("Unmasked PII risk")).toBeInTheDocument();
    expect(screen.getByText("Dataset")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();
  });

  it("clears results immediately when the input is emptied, without calling the API", () => {
    render(<GlobalSearch />);
    const input = getSearchInput();

    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.change(input, { target: { value: "" } });

    expect(mockedGet).not.toHaveBeenCalled();
    expect(screen.queryByText(/Searching/)).not.toBeInTheDocument();
  });

  it("navigates to a result's url on click", async () => {
    mockedGet.mockResolvedValue({ data: { results: RESULTS } });

    render(<GlobalSearch />);
    const input = getSearchInput();
    fireEvent.change(input, { target: { value: "customers" } });

    const item = await screen.findByText("public.customers");
    fireEvent.click(item);

    expect(pushMock).toHaveBeenCalledWith("/datasets/d1");
  });

  it("supports arrow-key navigation and Enter to select", async () => {
    mockedGet.mockResolvedValue({ data: { results: RESULTS } });

    render(<GlobalSearch />);
    const input = getSearchInput();
    fireEvent.change(input, { target: { value: "customers" } });

    await screen.findByText("public.customers");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(pushMock).toHaveBeenCalledWith("/risks");
  });

  it("groups results into Sources/Datasets/Columns sections in drill-down order", async () => {
    mockedGet.mockResolvedValue({ data: { results: TIERED_RESULTS } });

    render(<GlobalSearch />);
    const input = getSearchInput();
    fireEvent.change(input, { target: { value: "salesforce" } });

    await screen.findByText("Salesforce CRM");

    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByText("Datasets")).toBeInTheDocument();
    expect(screen.getByText("Columns")).toBeInTheDocument();
    expect(screen.getByText("public.customers")).toBeInTheDocument();
    expect(screen.getByText("email")).toBeInTheDocument();
  });

  it("navigates to a source result's ecosystem url on click", async () => {
    mockedGet.mockResolvedValue({ data: { results: TIERED_RESULTS } });

    render(<GlobalSearch />);
    const input = getSearchInput();
    fireEvent.change(input, { target: { value: "salesforce" } });

    const item = await screen.findByText("Salesforce CRM");
    fireEvent.click(item);

    expect(pushMock).toHaveBeenCalledWith("/ecosystem?sourceId=s1");
  });

  it("shows a no-matches message when the search returns nothing", async () => {
    mockedGet.mockResolvedValue({ data: { results: [] } });

    render(<GlobalSearch />);
    const input = getSearchInput();
    fireEvent.change(input, { target: { value: "zzz" } });

    expect(await screen.findByText(/No matches for/)).toBeInTheDocument();
  });

  it("closes the dropdown on outside click", async () => {
    mockedGet.mockResolvedValue({ data: { results: RESULTS } });

    render(
      <div>
        <div data-testid="outside">outside</div>
        <GlobalSearch />
      </div>
    );
    const input = getSearchInput();
    fireEvent.change(input, { target: { value: "customers" } });

    await screen.findByText("public.customers");

    act(() => {
      fireEvent.mouseDown(screen.getByTestId("outside"));
    });

    expect(screen.queryByText("public.customers")).not.toBeInTheDocument();
  });

  it("shows the mention dropdown when typing @, fetching from /api/mentions", async () => {
    mockedGet.mockResolvedValue({ data: { results: MENTION_RESULTS } });

    render(<GlobalSearch />);
    const input = getSearchInput();

    // Setting .value via fireEvent leaves the caret at the end of the
    // string by default, which is exactly where it'd be after typing.
    fireEvent.change(input, { target: { value: "revenue is @cust" } });

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith(
        "/api/mentions",
        expect.objectContaining({ params: { q: "cust", limit: 8 } })
      )
    );

    expect(await screen.findByText("public.customers")).toBeInTheDocument();
    expect(screen.getByText("Customer Lifetime Value")).toBeInTheDocument();
  });

  it("inserts the selected mention's exact label into the query on click", async () => {
    mockedGet.mockResolvedValue({ data: { results: MENTION_RESULTS } });

    render(<GlobalSearch />);
    const input = getSearchInput() as HTMLInputElement;

    fireEvent.change(input, { target: { value: "@cust" } });

    const item = await screen.findByText("public.customers");
    fireEvent.click(item);

    expect(input.value).toBe("@public.customers ");
  });
});
