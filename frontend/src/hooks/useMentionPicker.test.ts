import { act, renderHook, waitFor } from "@testing-library/react";

import api from "../services/api";
import { useMentionPicker } from "./useMentionPicker";
import type { MentionItem } from "../types/metadata";

jest.mock("../services/api", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedGet = api.get as jest.Mock;

const SUGGESTIONS: MentionItem[] = [
  { type: "dataset", id: "d1", label: "public.customers", subtitle: "public" },
  { type: "glossary_term", id: "g1", label: "Customer Lifetime Value", subtitle: "Glossary term" },
];

describe("useMentionPicker", () => {
  beforeEach(() => {
    mockedGet.mockReset();
  });

  it("stays closed for plain text with no @", () => {
    const { result } = renderHook(() => useMentionPicker());

    act(() => {
      result.current.onTextChange("what tables have PII?", 22);
    });

    expect(result.current.state.open).toBe(false);
    expect(mockedGet).not.toHaveBeenCalled();
  });

  it("opens and fetches /api/mentions when @ is typed, using the text after @ as the query", async () => {
    mockedGet.mockResolvedValue({ data: { results: SUGGESTIONS } });
    const { result } = renderHook(() => useMentionPicker());

    act(() => {
      result.current.onTextChange("who owns @cust", 14);
    });

    expect(result.current.state.open).toBe(true);
    expect(result.current.state.loading).toBe(true);

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith(
        "/api/mentions",
        expect.objectContaining({ params: { q: "cust", limit: 8 } })
      )
    );

    await waitFor(() => expect(result.current.state.loading).toBe(false));
    expect(result.current.state.suggestions).toEqual(SUGGESTIONS);
  });

  it("closes again once a space follows the @mention", () => {
    mockedGet.mockResolvedValue({ data: { results: SUGGESTIONS } });
    const { result } = renderHook(() => useMentionPicker());

    act(() => {
      result.current.onTextChange("who owns @cust", 14);
    });
    expect(result.current.state.open).toBe(true);

    act(() => {
      result.current.onTextChange("who owns @cust ", 15);
    });
    expect(result.current.state.open).toBe(false);
  });

  it("buildInsertion replaces the partial mention with the exact label plus a trailing space", () => {
    const { result } = renderHook(() => useMentionPicker());

    act(() => {
      result.current.onTextChange("who owns @cust", 14);
    });

    const inserted = result.current.buildInsertion("who owns @cust", 14, SUGGESTIONS[0]);

    expect(inserted).toEqual({
      value: "who owns @public.customers ",
      caret: "who owns @public.customers ".length,
    });
  });

  it("buildInsertion returns null when there's no active mention at the caret", () => {
    const { result } = renderHook(() => useMentionPicker());

    const inserted = result.current.buildInsertion("no mention here", 5, SUGGESTIONS[0]);

    expect(inserted).toBeNull();
  });

  it("handleKeyDown consumes arrow keys and Enter while open, and reports unconsumed keys as false", async () => {
    mockedGet.mockResolvedValue({ data: { results: SUGGESTIONS } });
    const { result } = renderHook(() => useMentionPicker());
    const onSelect = jest.fn();

    act(() => {
      result.current.onTextChange("who owns @cust", 14);
    });
    await waitFor(() => expect(result.current.state.loading).toBe(false));

    const preventDefault = jest.fn();

    act(() => {
      const consumed = result.current.handleKeyDown({ key: "ArrowDown", preventDefault }, onSelect);
      expect(consumed).toBe(true);
    });
    expect(preventDefault).toHaveBeenCalled();
    expect(result.current.state.activeIndex).toBe(0);

    act(() => {
      const consumed = result.current.handleKeyDown({ key: "Enter", preventDefault }, onSelect);
      expect(consumed).toBe(true);
    });
    expect(onSelect).toHaveBeenCalledWith(SUGGESTIONS[0]);

    // Closed now (Enter selected and callers are expected to call close()
    // themselves after acting on the selection) - but even while still
    // open, a key it doesn't handle (e.g. a plain letter) is reported
    // as not consumed so the caller's own input handling still runs.
    const lettersResult = renderHook(() => useMentionPicker());
    act(() => {
      lettersResult.result.current.onTextChange("@x", 2);
    });
    const consumedLetter = lettersResult.result.current.handleKeyDown(
      { key: "a", preventDefault: jest.fn() },
      onSelect
    );
    expect(consumedLetter).toBe(false);
  });

  it("close() resets to the initial closed state", async () => {
    mockedGet.mockResolvedValue({ data: { results: SUGGESTIONS } });
    const { result } = renderHook(() => useMentionPicker());

    act(() => {
      result.current.onTextChange("who owns @cust", 14);
    });
    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.close();
    });

    expect(result.current.state).toEqual({
      open: false,
      suggestions: [],
      activeIndex: -1,
      loading: false,
    });
  });
});
