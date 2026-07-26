import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import QueryLogPage from "./page";
import api from "../../services/api";

jest.mock("../../components/TopNav", () => ({
  __esModule: true,
  default: () => <div data-testid="top-nav" />,
}));

let mockUser = { id: "u1", email: "admin@example.com", role: "admin" };

jest.mock("../../hooks/useRequireAuth", () => ({
  useRequireAuth: () => ({ user: mockUser, loading: false }),
}));

jest.mock("../../services/api", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedGet = api.get as jest.Mock;

const REPORT = {
  window_days: 30,
  total_queries: 12,
  unanswered_count: 4,
  unanswered_rate: 33.3,
  top_unanswered: [
    {
      query_text: "who owns the mystery dataset?",
      count: 3,
      sources: ["ask"],
      last_asked_at: "2026-07-25T10:00:00Z",
    },
  ],
  top_overall: [
    {
      query_text: "who owns customers?",
      count: 5,
      sources: ["ask", "search"],
      last_asked_at: "2026-07-26T09:00:00Z",
    },
  ],
};

describe("QueryLogPage", () => {
  beforeEach(() => {
    mockedGet.mockReset();
    mockUser = { id: "u1", email: "admin@example.com", role: "admin" };
  });

  it("fetches and renders the report with default 30-day window", async () => {
    mockedGet.mockResolvedValue({ data: REPORT });

    render(<QueryLogPage />);

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith(
        "/api/query-log/report",
        expect.objectContaining({ params: { days: 30 } })
      )
    );

    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("33.3%")).toBeInTheDocument();
    expect(screen.getByText("who owns the mystery dataset?")).toBeInTheDocument();
    expect(screen.getByText("who owns customers?")).toBeInTheDocument();
    expect(screen.getByText("Ask + Search")).toBeInTheDocument();
  });

  it("refetches with a new window when a day-range button is clicked", async () => {
    mockedGet.mockResolvedValue({ data: REPORT });

    render(<QueryLogPage />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByText("7d"));

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith(
        "/api/query-log/report",
        expect.objectContaining({ params: { days: 7 } })
      )
    );
  });

  it("shows a friendly message instead of an error when the backend returns 403", async () => {
    mockedGet.mockRejectedValue({ response: { status: 403 } });

    render(<QueryLogPage />);

    expect(await screen.findByText(/only available to admins/)).toBeInTheDocument();
  });

  it("shows an empty state when there's nothing unanswered", async () => {
    mockedGet.mockResolvedValue({
      data: { ...REPORT, unanswered_count: 0, unanswered_rate: 0, top_unanswered: [] },
    });

    render(<QueryLogPage />);

    expect(await screen.findByText(/Nothing unanswered in this window/)).toBeInTheDocument();
  });
});
