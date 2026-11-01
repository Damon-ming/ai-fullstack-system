// search/src/hook/useSearchModalHook.ts
import { useMemo } from "react";
import { useSearchStore } from "@ming/store";
import { useHistory } from "@ming/feature-history-api";
import { useSearch } from "./SearchHook";
import type { HistoryItem } from "@ming/feature-history-api";

/**
 * SearchModal 业务编排 hook —— 跨模块获取历史数据 + 搜索过滤。
 * hook/ 层是跨模块业务调用的唯一发起层（通过 feature-history-api）。
 */
export function useSearchModalHook() {
  const open = useSearchStore((s) => s.open);
  const keyword = useSearchStore((s) => s.keyword);
  const setKeyword = useSearchStore((s) => s.setKeyword);
  const closeSearch = useSearchStore((s) => s.closeSearch);
  const { list: historyList } = useHistory();
  const results = useMemo(
    () => useSearch<HistoryItem>(historyList, { keyword }),
    [historyList, keyword],
  );

  return { open, keyword, setKeyword, closeSearch, results };
}
