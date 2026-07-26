"use client";

import { useRef, useState } from "react";

import api from "../services/api";
import type { MentionItem, MentionResponse } from "../types/metadata";

const DEBOUNCE_MS = 200;

// Matches an "@" that starts either at the beginning of the text or
// right after whitespace, followed by zero or more non-space,
// non-"@" characters up to the cursor - i.e. the mention is still
// being actively typed (no space after it yet). Anything after the
// cursor is left untouched.
const MENTION_PATTERN = /(?:^|\s)@([^\s@]*)$/;

type MentionMatch = {
  start: number; // index of the "@" itself
  query: string;
};

type MentionPickerState = {
  open: boolean;
  suggestions: MentionItem[];
  activeIndex: number;
  loading: boolean;
};

const INITIAL_STATE: MentionPickerState = {
  open: false,
  suggestions: [],
  activeIndex: -1,
  loading: false,
};

function detectMention(value: string, caret: number): MentionMatch | null {
  const uptoCaret = value.slice(0, caret);
  const match = uptoCaret.match(MENTION_PATTERN);

  if (!match) return null;

  const query = match[1];
  const start = caret - query.length - 1;

  return { start, query };
}

/**
 * Shared "@" mention picker for any plain text input/textarea - typing
 * "@" pops an autocomplete of catalog entities (backed by
 * GET /api/mentions, name-prefix matching, not the TF-IDF relevance
 * search /api/search uses) so a question or search can reference one
 * precisely instead of relying on keyword matching downstream to land
 * on the right dataset/glossary term/etc.
 *
 * Deliberately does NOT own the input's value/onChange - the caller
 * (GlobalSearch, the Ask page) keeps doing that itself and just also
 * calls onTextChange() with the latest value + caret position on
 * every change, and handleKeyDown()'s return value tells it whether
 * the keystroke was consumed by the mention dropdown (so the caller's
 * own Enter-submits/Escape-closes logic doesn't also fire).
 */
export function useMentionPicker() {
  const [state, setState] = useState<MentionPickerState>(INITIAL_STATE);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  function close() {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setState(INITIAL_STATE);
  }

  function onTextChange(value: string, caret: number) {
    const mention = detectMention(value, caret);

    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!mention) {
      setState(INITIAL_STATE);
      return;
    }

    setState((prev) => ({ ...prev, open: true, loading: true, activeIndex: -1 }));

    debounceRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current;

      try {
        const response = await api.get<MentionResponse>("/api/mentions", {
          params: { q: mention.query, limit: 8 },
        });

        if (requestId === requestIdRef.current) {
          setState((prev) => ({ ...prev, suggestions: response.data.results, loading: false }));
        }
      } catch (error) {
        console.error(error);
        if (requestId === requestIdRef.current) {
          setState((prev) => ({ ...prev, suggestions: [], loading: false }));
        }
      }
    }, DEBOUNCE_MS);
  }

  function moveActive(delta: number) {
    setState((prev) => {
      if (prev.suggestions.length === 0) return prev;
      const next = (prev.activeIndex + delta + prev.suggestions.length) % prev.suggestions.length;
      return { ...prev, activeIndex: next };
    });
  }

  /**
   * Given the input's current value/caret and the chosen suggestion,
   * returns the new full text (mention text replaced with the exact
   * entity label, plus a trailing space) and where the caret should
   * land afterward. Returns null if there's no active "@" mention to
   * replace at that caret position (shouldn't normally happen, since
   * this is only called while the dropdown is open).
   */
  function buildInsertion(
    value: string,
    caret: number,
    item: MentionItem
  ): { value: string; caret: number } | null {
    const mention = detectMention(value, caret);
    if (!mention) return null;

    const insertText = `@${item.label} `;
    const newValue = value.slice(0, mention.start) + insertText + value.slice(caret);
    const newCaret = mention.start + insertText.length;

    return { value: newValue, caret: newCaret };
  }

  /**
   * Call from the input's onKeyDown before running any of the
   * caller's own key handling. Returns true if the key was consumed
   * by the mention dropdown (arrow nav, escape, or enter/tab while a
   * suggestion is highlighted) - the caller should preventDefault and
   * stop there. `onSelect` is only invoked for Enter/Tab, since
   * arrow/escape don't pick anything.
   */
  function handleKeyDown(
    event: { key: string; preventDefault: () => void },
    onSelect: (item: MentionItem) => void
  ): boolean {
    if (!state.open || state.suggestions.length === 0) return false;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveActive(1);
      return true;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveActive(-1);
      return true;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return true;
    }

    if (event.key === "Enter" || event.key === "Tab") {
      const target = state.suggestions[state.activeIndex >= 0 ? state.activeIndex : 0];
      if (target) {
        event.preventDefault();
        onSelect(target);
        return true;
      }
    }

    return false;
  }

  return {
    state,
    onTextChange,
    handleKeyDown,
    buildInsertion,
    close,
  };
}
