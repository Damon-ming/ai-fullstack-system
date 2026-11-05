// search/src/hook/useSearchModalHook.ts
import { useEffect, useMemo, useState } from "react";
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
  const { list, loadAll } = useHistory();

  // 抽屉列表只加载最近几页；搜索必须覆盖全部历史，否则早期会话搜不到
  const [fullList, setFullList] = useState<HistoryItem[]>([]);
  useEffect(() => {
    if (!open) {
      // 关闭时清空，避免下次打开显示已删除的会话
      setFullList([]);
      return;
    }
    let cancelled = false;
    void loadAll().then((items) => {
      if (!cancelled) setFullList(items);
    });
    return () => {
      cancelled = true;
    };
  }, [open, loadAll]);

  // 全量未就绪前先搜已加载部分，就绪后切换为全量
  const searchingList = fullList.length > 0 ? fullList : list;
  const results = useMemo(
    () => useSearch<HistoryItem>(searchingList, { keyword }),
    [searchingList, keyword],
  );

  return { open, keyword, setKeyword, closeSearch, results };
}
