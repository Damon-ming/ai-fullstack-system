import { useMemo } from "react";
import type { SearchOptions, SearchResultItem } from "../api";

export const searchItems = <T extends SearchResultItem>(
  items: T[],
  keyword: string,
) => {
  const normalized = keyword.trim().toLocaleLowerCase();
  return normalized
    ? items.filter(
        (item) =>
          item.title.toLocaleLowerCase().includes(normalized) ||
          (item.turns || []).some(
            (turn) =>
              turn.query.toLocaleLowerCase().includes(normalized) ||
              turn.content.toLocaleLowerCase().includes(normalized),
          ),
      )
    : items;
};

export function useSearch<
  T extends {
    title: string;
    turns?: Array<{ query: string; content: string }>;
  },
>(items: T[], options: SearchOptions) {
  return useMemo(
    () => searchItems(items, options.keyword),
    [items, options.keyword],
  );
}
