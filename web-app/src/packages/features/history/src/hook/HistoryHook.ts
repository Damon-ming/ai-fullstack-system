// web-app/src/packages/features/history/src/hook/HistoryHook.ts
import { useCallback, useMemo } from "react";
import type { HistoryMessage } from "../api/types";
import {
  useHistoryListQuery,
  useSaveHistoryMutation,
  useRemoveHistoryMutation,
  historyStore,
} from "../api";
import { unpackList } from "../api/unpack";
import { getCalendarDayDistance, getMonthParts } from "@ming/core-util";

// ---------------------------------------------------------------------------
// 业务逻辑（纯函数，UI 层特有，不属于 core 时间工具）
// ---------------------------------------------------------------------------

function getHistoryGroupLabel(createdAt: number): string {
  const days = getCalendarDayDistance(createdAt);
  if (days === 0) return "今天";
  if (days === 1) return "昨天";
  if (days < 7) return "1周内";
  if (days < 30) return "30天内";
  const { year, month } = getMonthParts(createdAt);
  return `${year}.${month}`;
}

// ---------------------------------------------------------------------------
// Hook：编排 api 层预配置 hook + 业务逻辑 + 数据解析
// ---------------------------------------------------------------------------

export function useHistory() {
  // api 层 hook 已经封装了 query/mutation + 缓存失效，此处只做编排
  const listQuery = useHistoryListQuery();
  const list = useMemo(() => unpackList(listQuery.data), [listQuery.data]);

  const saveMutation = useSaveHistoryMutation();
  const removeMutation = useRemoveHistoryMutation();

  const saveMessages = useCallback(
    (title: string, messages: HistoryMessage[]) => {
      saveMutation.mutate({ title, messages });
    },
    [saveMutation],
  );

  const remove = useCallback(
    (id: string) => {
      removeMutation.mutate(id);
    },
    [removeMutation],
  );

  // 业务逻辑：按时间分组（UI 层需求，非通用工具）
  const groups = useMemo(() => {
    const grouped = new Map<string, typeof list>();
    for (const item of [...list].sort((a, b) => b.createdAt - a.createdAt)) {
      const label = getHistoryGroupLabel(item.createdAt);
      grouped.set(label, [...(grouped.get(label) || []), item]);
    }
    return [...grouped.entries()].map(([label, items]) => ({ label, items }));
  }, [list]);

  return {
    list,
    groups,
    loading: listQuery.isLoading,
    getMessages: historyStore.messages,
    saveMessages,
    remove,
    add: historyStore.add,
  };
}

/** 非 React 上下文的同步调用（返回 Promise，供事件回调等场景使用）。 */
export const historyActions = {
  list: historyStore.list,
  messages: historyStore.messages,
  saveMessages: historyStore.saveMessages,
  add: historyStore.add,
  remove: historyStore.remove,
};
