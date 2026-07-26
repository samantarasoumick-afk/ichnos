import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import AskPage from "./page";
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
  default: { get: jest.fn(), post: jest.fn() },
}));

const mockedGet = api.get as jest.Mock;
const mockedPost = api.post as jest.Mock;

const MENTION_SUGGESTIONS = [
  { type: "dataset", id: "d1", label: "public.customers", subtitle: "public" },
];

function getQuestionInput() {
  return screen.getByPlaceholderText(/Ask about your catalog/);
}

describe("AskPage @ mentions", () => {
  beforeEach(() => {
    mockedGet.mockReset();
    mockedPost.mockReset();
  });

  it("does not show a mention dropdown for plain text", () => {
    render(<AskPage />);
    fireEvent.change(getQuestionInput(), { target: { value: "who owns customers?" } });

    expect(mockedGet).not.toHaveBeenCalled();
  });

  it("shows suggestions from /api/mentions when @ is typed and inserts the chosen label on click", async () => {
    mockedGet.mockResolvedValue({ data: { results: MENTION_SUGGESTIONS } });

    render(<AskPage />);
    const input = getQuestionInput() as HTMLInputElement;

    fireEvent.change(input, { target: { value: "who owns @cust" } });

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith(
        "/api/mentions",
        expect.objectContaining({ params: { q: "cust", limit: 8 } })
      )
    );

    const suggestion = await screen.findByText("public.customers");
    fireEvent.click(suggestion);

    expect(input.value).toBe("who owns @public.customers ");
  });

  it("Enter selects the highlighted mention instead of submitting the question", async () => {
    mockedGet.mockResolvedValue({ data: { results: MENTION_SUGGESTIONS } });

    render(<AskPage />);
    const input = getQuestionInput() as HTMLInputElement;

    fireEvent.change(input, { target: { value: "who owns @cust" } });
    await screen.findByText("public.customers");

    fireEvent.keyDown(input, { key: "Enter" });

    expect(input.value).toBe("who owns @public.customers ");
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it("Enter still submits the question normally once no mention is active", async () => {
    mockedPost.mockResolvedValue({ data: { answer: "Steward is Jane Doe.", sources: [] } });

    render(<AskPage />);
    const input = getQuestionInput();

    fireEvent.change(input, { target: { value: "who owns customers?" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1));
    expect(mockedPost).toHaveBeenCalledWith(
      "/api/assistant/ask",
      expect.objectContaining({ query: "who owns customers?" })
    );
  });
});
