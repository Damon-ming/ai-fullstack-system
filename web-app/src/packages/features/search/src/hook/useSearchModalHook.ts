// search/src/hook/useSearchModalHook.ts
import { useEffect, useState } from "react";
import { useSearchStore } from "@ming/store";
import { searchHistory } from "../api";
import type { SearchResultItem } from "../api";

/**
 * SearchModal business orchestration: debounced server-side history search.
 */
export function useSearchModalHook() {
  const open = useSearchStore((s) => s.open);
  const keyword = useSearchStore((s) => s.keyword);
  const setKeyword = useSearchStore((s) => s.setKeyword);
  const closeSearch = useSearchStore((s) => s.closeSearch);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  useEffect(() => {
    const normalized = keyword.trim();
    if (!open || !normalized) { setResults([]); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void searchHistory({ keyword: normalized }).then((response) => {
        if (!cancelled) setResults(response.data ?? []);
      }).catch(() => { if (!cancelled) setResults([]); });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, keyword]);

  return { open, keyword, setKeyword, closeSearch, results };
}
