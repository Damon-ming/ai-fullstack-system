// web-app/src/packages/features/history/src/hook/HistoryHook.ts
import { useCallback, useMemo } from "react";
import type { HistoryItem, HistoryMessage } from "../api/types";
import {
  fetchList,
  fetchMessages,
  saveToServer,
  addConversation,
  removeFromServer,
  useHistoryListQuery,
  useSaveHistoryMutation,
  useRemoveHistoryMutation,
} from "../api";
import { getCalendarDayDistance, getMonthParts } from "@ming/core-util";

// 内部类型 —— 用于数据解包函数参数
interface DataEnvelope {
  data?: unknown;
}
interface HistoryApiRecord {
  id: unknown;
  title?: unknown;
  updatedAt?: string;
  updated_at?: string;
  createdAt?: unknown;
  created_at?: unknown;
  messages?: unknown;
}

// ---------------------------------------------------------------------------
// 数据解包 —— 服务端响应 → 前端业务对象（业务逻辑，非纯网络层）
// ---------------------------------------------------------------------------

function parseTimestamp(raw: unknown): number {
  if (!raw) return Date.now();
  const ms = new Date(raw as string).getTime();
  return Number.isNaN(ms) ? Date.now() : ms;
}

function unpackDetail(res: DataEnvelope | undefined): unknown {
  const d = res?.data as { conversation?: unknown };
  return d?.conversation ?? d;
}

function parseListRecord(item: unknown): HistoryItem {
  const obj = item as HistoryApiRecord;
  return {
    id: String(obj.id),
    title: String(obj.title ?? ""),
    meta: String(obj.updatedAt || obj.updated_at || ""),
    createdAt: parseTimestamp(obj.createdAt || obj.created_at),
    messages: [],
  };
}

function parseMessages(raw: unknown): HistoryMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((m: { id: unknown; text?: unknown; role: unknown }) => ({
    id: String(m.id),
    text: String(m.text ?? ""),
    role: m.role === "assistant" ? "assistant" : "user",
  }));
}

function unpackList(res: DataEnvelope | undefined): HistoryItem[] {
  const items = (res?.data ?? []) as unknown[];
  return items.map(parseListRecord);
}

async function fetchAndUnpackMessages(id: string): Promise<HistoryMessage[]> {
  const res = await fetchMessages(id);
  const detail = unpackDetail(res) as { messages?: unknown } | undefined;
  return parseMessages(detail?.messages);
}

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

  const groups = useMemo(() => {
    const grouped = new Map<string, typeof list>();
    for (const item of [...list].sort((a, b) => b.createdAt - a.createdAt)) {
      const label = getHistoryGroupLabel(item.createdAt);
      grouped.set(label, [...(grouped.get(label) || []), item]);
    }
    return [...grouped.entries()].map(([label, items]) => ({ label, items }));
  }, [list]);

  const refresh = useCallback(
    () => listQuery.refetch(),
    [listQuery.refetch],
  );

  return {
    list,
    groups,
    loading: listQuery.isLoading,
    getMessages: fetchAndUnpackMessages,
    saveMessages,
    remove,
    add: addConversation,
    /** 重新拉取历史列表（服务端新建会话后刷新抽屉用） */
    refresh,
  };
}

/** 非 React 上下文的同步调用（返回 Promise，供事件回调等场景使用）。 */
export const historyActions = {
  list: fetchList,
  messages: fetchAndUnpackMessages,
  saveMessages: saveToServer,
  add: addConversation,
  remove: removeFromServer,
};
