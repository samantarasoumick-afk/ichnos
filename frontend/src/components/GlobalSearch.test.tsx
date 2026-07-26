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
    const input = screen.getByPlaceholderText("Search everything...");

    fireEvent.change(input, { target: { value: "customers" } });

    // Nothing fired yet - still inside the debounce window.
    expect(mockedGet).not.toHaveBeenCalled();

    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
    expect(mockedGet).toHaveBeenCalledWith(
      "/api/search",
      expect.objectContaining({ params: { q: "customers", limit: 8 } })
    );

    expect(await screen.findByText("public.customers")).toBeInTheDocument();
    expect(screen.getByText("Unmasked PII risk")).toBeInTheDocument();
    expect(screen.getByText("Dataset")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();
  });

  it("clears results immediately when the input is emptied, without calling the API", () => {
    render(<GlobalSearch />);
    const input = screen.getByPlaceholderText("Search everything...");

    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.change(input, { target: { value: "" } });

    expect(mockedGet).not.toHaveBeenCalled();
    expect(screen.queryByText(/Searching/)).not.toBeInTheDocument();
  });

  it("navigates to a result's url on click", async () => {
    mockedGet.mockResolvedValue({ data: { results: RESULTS } });

    render(<GlobalSearch />);
    const input = screen.getByPlaceholderText("Search everything...");
    fireEvent.change(input, { target: { value: "customers" } });

    const item = await screen.findByText("public.customers");
    fireEvent.click(item);

    expect(pushMock).toHaveBeenCalledWith("/datasets/d1");
  });

  it("supports arrow-key navigation and Enter to select", async () => {
    mockedGet.mockResolvedValue({ data: { results: RESULTS } });

    render(<GlobalSearch />);
    const input = screen.getByPlaceholderText("Search everything...");
    fireEvent.change(input, { target: { value: "customers" } });

    await screen.findByText("public.customers");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(pushMock).toHaveBeenCalledWith("/risks");
  });

  it("shows a no-matches message when the search returns nothing", async () => {
    mockedGet.mockResolvedValue({ data: { results: [] } });

    render(<GlobalSearch />);
    const input = screen.getByPlaceholderText("Search everything...");
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
    const input = screen.getByPlaceholderText("Search everything...");
    fireEvent.change(input, { target: { value: "customers" } });

    await screen.findByText("public.customers");

    act(() => {
      fireEvent.mouseDown(screen.getByTestId("outside"));
    });

    expect(screen.queryByText("public.customers")).not.toBeInTheDocument();
  });
});
