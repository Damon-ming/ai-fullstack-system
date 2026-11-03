// web-app/src/packages/features/history/src/hook/HistoryHook.ts
import { useCallback, useMemo } from "react";
import type { HistoryItem, HistoryTurn } from "../api/types";
import {
  fetchList,
  fetchTurns,
  saveToServer,
  addConversation,
  removeFromServer,
  useHistoryListQuery,
  useSaveHistoryMutation,
  useRemoveHistoryMutation,
} from "../api";
import { getCalendarDayDistance, getMonthParts } from "@ming/core-util";

/** 与 @ming/store 的 ChatMessage 结构兼容（纯类型，避免 feature → store 反向依赖） */
export interface HistoryChatMessage {
  id: string;
  text: string;
  role: "user" | "assistant";
  reasoning?: string;
}

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
  turns?: unknown;
}
interface HistoryTurnRecord {
  turn_id?: unknown;
  turnId?: unknown;
  query?: unknown;
  reasoning?: unknown;
  content?: unknown;
  query_at?: unknown;
  queryAt?: unknown;
  first_token_at?: unknown;
  firstTokenAt?: unknown;
  reasoning_done_at?: unknown;
  reasoningDoneAt?: unknown;
  answered_at?: unknown;
  answeredAt?: unknown;
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
    turns: [],
  };
}

function parseTurn(raw: unknown): HistoryTurn {
  const t = raw as HistoryTurnRecord;
  return {
    turnId: String(t.turn_id ?? t.turnId ?? ""),
    query: String(t.query ?? ""),
    reasoning: String(t.reasoning ?? ""),
    content: String(t.content ?? ""),
    queryAt: String(t.query_at ?? t.queryAt ?? ""),
    firstTokenAt: String(t.first_token_at ?? t.firstTokenAt ?? ""),
    reasoningDoneAt: String(t.reasoning_done_at ?? t.reasoningDoneAt ?? ""),
    answeredAt: String(t.answered_at ?? t.answeredAt ?? ""),
  };
}

function parseTurns(raw: unknown): HistoryTurn[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(parseTurn);
}

function unpackList(res: DataEnvelope | undefined): HistoryItem[] {
  const items = (res?.data ?? []) as unknown[];
  return items.map(parseListRecord);
}

async function fetchAndUnpackTurns(id: string): Promise<HistoryTurn[]> {
  const res = await fetchTurns(id);
  const detail = unpackDetail(res) as { turns?: unknown } | undefined;
  return parseTurns(detail?.turns);
}

/**
 * 轮次 → 聊天消息：一个轮次展开成「用户提问 + 助手回答」两条消息，
 * 推理文本挂到助手消息上，保证历史重载后推理过程不丢。
 */
export function turnsToChatMessages(
  turns: HistoryTurn[],
): HistoryChatMessage[] {
  const messages: HistoryChatMessage[] = [];
  for (const turn of turns) {
    messages.push({ id: `${turn.turnId}_q`, text: turn.query, role: "user" });
    messages.push({
      id: `${turn.turnId}_a`,
      text: turn.content,
      role: "assistant",
      reasoning: turn.reasoning || undefined,
    });
  }
  return messages;
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

  const saveTurns = useCallback(
    (title: string, turns: HistoryTurn[]) => {
      saveMutation.mutate({ title, turns });
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

  const refresh = useCallback(() => listQuery.refetch(), [listQuery.refetch]);

  return {
    list,
    groups,
    loading: listQuery.isLoading,
    getTurns: fetchAndUnpackTurns,
    saveTurns,
    remove,
    add: addConversation,
    /** 重新拉取历史列表（服务端新建会话后刷新抽屉用） */
    refresh,
  };
}

/** 非 React 上下文的同步调用（返回 Promise，供事件回调等场景使用）。 */
export const historyActions = {
  list: fetchList,
  turns: fetchAndUnpackTurns,
  saveTurns: saveToServer,
  add: addConversation,
  remove: removeFromServer,
};
