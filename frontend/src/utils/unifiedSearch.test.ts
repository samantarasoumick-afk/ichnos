import api from "../services/api";
import { fetchInlineAnswer, isQuestionLike } from "./unifiedSearch";

jest.mock("../services/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

const mockedPost = api.post as jest.Mock;

describe("isQuestionLike", () => {
  it("returns false for an empty or whitespace-only string", () => {
    expect(isQuestionLike("")).toBe(false);
    expect(isQuestionLike("   ")).toBe(false);
  });

  it("returns true for anything ending in a question mark", () => {
    expect(isQuestionLike("customers table?")).toBe(true);
  });

  it("returns true for common interrogative openers, with or without a trailing ?", () => {
    expect(isQuestionLike("who owns customers")).toBe(true);
    expect(isQuestionLike("Does public.customers have PII?")).toBe(true);
    expect(isQuestionLike("What is downstream of orders")).toBe(true);
    expect(isQuestionLike("how is our governance maturity")).toBe(true);
  });

  it("returns false for a plain lookup term", () => {
    expect(isQuestionLike("customers")).toBe(false);
    expect(isQuestionLike("Salesforce CRM")).toBe(false);
    expect(isQuestionLike("public.customers")).toBe(false);
  });
});

describe("fetchInlineAnswer", () => {
  beforeEach(() => {
    mockedPost.mockReset();
  });

  it("posts to /api/assistant/ask with a single-turn (empty history) payload", async () => {
    mockedPost.mockResolvedValue({
      data: { answer: "public.customers is owned by Growth Team.", sources: [], follow_up_suggestions: [] },
    });

    const result = await fetchInlineAnswer("who owns customers?");

    expect(mockedPost).toHaveBeenCalledWith("/api/assistant/ask", {
      query: "who owns customers?",
      history: [],
    });
    expect(result?.answer).toBe("public.customers is owned by Growth Team.");
  });

  it("returns null instead of throwing when the request fails", async () => {
    mockedPost.mockRejectedValue(new Error("network error"));
    const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});

    const result = await fetchInlineAnswer("who owns customers?");

    expect(result).toBeNull();
    consoleErrorSpy.mockRestore();
  });
});
