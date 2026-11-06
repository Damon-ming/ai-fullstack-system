// web-app/src/packages/features/history/src/hook/HistoryHook.ts
import { useCallback, useMemo } from "react";
import type { HistoryItem, HistoryTurn } from "../api";
import {
  fetchList,
  fetchTurns,
  removeFromServer,
  useHistoryListInfiniteQuery,
  useRemoveHistoryMutation,
} from "../api";
import { getCalendarDayDistance, getMonthParts } from "@ming/core-util";
import { createLogger } from "@ming/core-log";
import { useChatMessageStore, useChatUiStore } from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";
import type { HistoryChatMessage } from "./types";

export type { HistoryChatMessage } from "./types";

const log = createLogger("feature-history/hook");

// 内部类型 —— 用于数据解包函数参数（后端统一 camelCase，无需双口径兼容）
interface DataEnvelope {
  data?: unknown;
}
interface HistoryApiRecord {
  conversationId?: unknown;
  title?: unknown;
  createdAt?: unknown;
  updatedAt?: unknown;
  turns?: unknown;
}
interface HistoryTurnRecord {
  turnId?: unknown;
  query?: unknown;
  reasoning?: unknown;
  content?: unknown;
  errorMsg?: unknown;
  queryAt?: unknown;
  firstTokenAt?: unknown;
  reasoningDoneAt?: unknown;
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

/** ISO 时间字符串 → Unix 秒；空值/非法值返回 undefined（不展示时间戳，而不是显示当前时间） */
function parseQueryAt(raw: unknown): number | undefined {
  if (!raw) return undefined;
  const ms = new Date(raw as string).getTime();
  return Number.isNaN(ms) ? undefined : Math.floor(ms / 1000);
}

function unpackDetail(res: DataEnvelope | undefined): unknown {
  const d = res?.data as { conversation?: unknown };
  return d?.conversation ?? d;
}

function parseListRecord(item: unknown): HistoryItem {
  const obj = item as HistoryApiRecord;
  return {
    conversationId: String(obj.conversationId ?? ""),
    title: String(obj.title ?? ""),
    createdAt: String(obj.createdAt ?? ""),
    updatedAt: String(obj.updatedAt ?? ""),
    turns: [],
  };
}

function parseTurn(raw: unknown): HistoryTurn {
  const t = raw as HistoryTurnRecord;
  return {
    turnId: String(t.turnId ?? ""),
    query: String(t.query ?? ""),
    reasoning: String(t.reasoning ?? ""),
    content: String(t.content ?? ""),
    errorMsg: String(t.errorMsg ?? ""),
    queryAt: String(t.queryAt ?? ""),
    firstTokenAt: String(t.firstTokenAt ?? ""),
    reasoningDoneAt: String(t.reasoningDoneAt ?? ""),
    answeredAt: String(t.answeredAt ?? ""),
  };
}

function parseTurns(raw: unknown): HistoryTurn[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(parseTurn);
}

async function fetchAndUnpackTurns(id: string): Promise<HistoryTurn[]> {
  try {
    const res = await fetchTurns(id);
    const detail = unpackDetail(res) as { turns?: unknown } | undefined;
    return parseTurns(detail?.turns);
  } catch (e) {
    // 拉取失败按空会话处理：调用方仍需切换视图，不能静默保留旧会话内容
    log.error("fetch turns failed", e);
    return [];
  }
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
    messages.push({
      id: `${turn.turnId}_q`,
      content: turn.query,
      role: "user",
    });
    // 空气泡清理：服务端未交付任何内容（无正文 / 推理 / 异常提示）时不展示助手消息
    if (turn.content || turn.reasoning || turn.errorMsg) {
      messages.push({
        id: `${turn.turnId}_a`,
        content: turn.content,
        role: "assistant",
        reasoning: turn.reasoning || undefined,
        errorMsg: turn.errorMsg || undefined,
        turnId: turn.turnId,
        queryAt: parseQueryAt(turn.queryAt),
        // 历史轮次已是终态：标题用「推理过程」，折叠口径与流式正文开始时一致
        isReasoning: false,
        reasoningCollapsed: true,
      });
    }
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
  const infiniteQuery = useHistoryListInfiniteQuery();
  const pages = infiniteQuery.data?.pages;

  // 累积所有已加载页（后端按 updated_at 倒序分页）
  const list = useMemo(
    () =>
      (pages ?? [])
        .flatMap((page) => (page.data ?? []) as unknown[])
        .map(parseListRecord),
    [pages],
  );

  const removeMutation = useRemoveHistoryMutation();

  const remove = useCallback(
    (id: string) => {
      removeMutation.mutate(id);
    },
    [removeMutation],
  );

  const groups = useMemo(() => {
    const grouped = new Map<string, typeof list>();
    // 与服务端列表口径一致：按 updatedAt 倒序分组
    const sorted = [...list].sort(
      (a, b) => parseTimestamp(b.updatedAt) - parseTimestamp(a.updatedAt),
    );
    for (const item of sorted) {
      const label = getHistoryGroupLabel(parseTimestamp(item.updatedAt));
      grouped.set(label, [...(grouped.get(label) || []), item]);
    }
    return [...grouped.entries()].map(([label, items]) => ({ label, items }));
  }, [list]);

  const refresh = useCallback(
    () => infiniteQuery.refetch(),
    [infiniteQuery.refetch],
  );

  /** 是否还有未加载的会话 */
  const hasMore = infiniteQuery.hasNextPage ?? false;
  const isLoadingMore = infiniteQuery.isFetchingNextPage;

  /** 加载下一页（抽屉滚动到底部时调用） */
  const loadMore = useCallback(() => {
    if (infiniteQuery.hasNextPage && !infiniteQuery.isFetchingNextPage) {
      void infiniteQuery.fetchNextPage();
    }
  }, [
    infiniteQuery.hasNextPage,
    infiniteQuery.isFetchingNextPage,
    infiniteQuery.fetchNextPage,
  ]);

  /**
   * 拉取全部会话（搜索等需要全量数据的场景）。
   * 抽屉列表只加载最近几页，搜索必须覆盖全部历史，否则早期会话搜不到。
   */
  const loadAll = useCallback(async (): Promise<HistoryItem[]> => {
    const all: HistoryItem[] = [];
    const pageSize = 100;
    // 上限 100 页（10000 条）防御异常情况下无限循环
    for (let page = 1; page <= 100; page += 1) {
      const res = await fetchList(page, pageSize);
      const items = ((res.data ?? []) as unknown[]).map(parseListRecord);
      all.push(...items);
      if (items.length < pageSize) break;
    }
    return all;
  }, []);

  return {
    list,
    groups,
    loading: infiniteQuery.isLoading,
    hasMore,
    isLoadingMore,
    loadMore,
    loadAll,
    remove,
    /** 重新拉取历史列表（服务端新建会话后刷新抽屉用） */
    refresh,
  };
}

/**
 * 切换会话：取消进行中的流 → 拉取目标会话轮次 → 转消息 → 更新 activeId → 重置 sessionId。
 *
 * 抽屉会话列表点击与搜索结果选中共用同一条恢复链路，统一收敛在此，避免两处逻辑漂移。
 * 无论有无轮次都切换视图：空会话 / 拉取失败是合法状态，
 * 静默保留旧会话内容会让用户误以为在看新会话。
 */
export function useSelectConversation() {
  const abortStream = useChatMessageStore((s) => s.abortStream);
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const resetSession = useChatUiStore((s) => s.resetSession);
  const setActiveConversationId = useHistoryStore((s) => s.setActiveConversationId);

  return useCallback(
    async (conversationId: string) => {
      // 切换会话前取消进行中的流，避免旧流的 sending 状态锁住新会话
      abortStream();
      const turns = await fetchAndUnpackTurns(conversationId);
      setMessages(turnsToChatMessages(turns));
      setActiveConversationId(conversationId);
      resetSession();
    },
    [abortStream, setMessages, resetSession, setActiveConversationId],
  );
}

/** 非 React 上下文的同步调用（返回 Promise，供事件回调等场景使用）。 */
export const historyActions = {
  list: fetchList,
  turns: fetchAndUnpackTurns,
  remove: removeFromServer,
};
