// web-app/src/packages/features/history/src/api/history.api.ts
/**
 * 历史记录 API 层 —— 仅负责：网络请求、打印日志、透传原始 DataApiResponse。
 *
 * 包含：
 *   - 纯 fetcher（HTTP + 日志）
 *   - query/mutation hook 工厂（使用 queryFactory，仅配置缓存策略，不含业务逻辑）
 *
 * 不包含：
 *   - 数据解包 / 字段映射（由 hook 层 HistoryHook 负责）
 *   - 业务编排（由 hook 层负责）
 */

import { dataApi, queryFactory } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import { createLogger } from "@ming/core-log";
import type { HistoryMessage, SaveHistoryRequest } from "./types";

const log = createLogger("history/api");

// ---------------------------------------------------------------------------
// 缓存 key
// ---------------------------------------------------------------------------

const HISTORY_LIST_KEY = ["history", "list"] as const;

// ---------------------------------------------------------------------------
// 纯 fetcher —— 只发请求 + 日志，返回完整 DataApiResponse 透传给 hook 层
// ---------------------------------------------------------------------------

export async function fetchList(): Promise<DataApiResponse<unknown[]>> {
  log.debug("fetch history list");
  return dataApi.get<unknown[]>("/api/history/list/v1", {
    params: { page: 1, page_size: 100 },
  });
}

export async function fetchMessages(
  id: string,
): Promise<DataApiResponse<unknown>> {
  log.debug("fetch history messages", { id });
  return dataApi.get<unknown>(`/api/history/v1/${id}`);
}

export async function saveToServer(
  params: SaveHistoryRequest,
): Promise<DataApiResponse<unknown>> {
  log.debug("save history", { title: params.title });
  return dataApi.post<unknown>("/api/history/save/v1", params);
}

export async function addConversation(
  title: string,
): Promise<DataApiResponse<unknown>> {
  log.debug("add conversation", { title });
  return dataApi.post<unknown>("/api/history/save/v1", { title, messages: [] });
}

export async function removeFromServer(
  id: string,
): Promise<DataApiResponse<void>> {
  log.debug("remove history", { id });
  return dataApi.delete<void>(`/api/history/v1/${id}`);
}

// ---------------------------------------------------------------------------
// 预配置 query/mutation hook（仅配置缓存策略，不含业务逻辑）
// ---------------------------------------------------------------------------

/** 列表查询 hook —— 30s 内不重新拉取 */
export const useHistoryListQuery = queryFactory.createQueryHook<unknown[]>(
  HISTORY_LIST_KEY,
  fetchList,
  { staleTime: 30 * 1000 },
);

/** 保存 mutation —— 成功后自动刷新列表 */
export const useSaveHistoryMutation = queryFactory.createMutationHook<
  unknown,
  SaveHistoryRequest
>(saveToServer, { invalidateKeys: [HISTORY_LIST_KEY] });

/** 删除 mutation —— 成功后自动刷新列表 */
export const useRemoveHistoryMutation = queryFactory.createMutationHook<
  void,
  string
>(removeFromServer, { invalidateKeys: [HISTORY_LIST_KEY] });

// ---------------------------------------------------------------------------
// 同步调用对象（非 React 上下文使用，不走缓存）—— 纯透传 fetcher
// ---------------------------------------------------------------------------

export const historyStore = {
  list: fetchList,
  messages: fetchMessages,
  saveMessages: (title: string, messages: HistoryMessage[]) =>
    saveToServer({ title, messages }),
  add: addConversation,
  remove: removeFromServer,
};
