// web-app/src/packages/features/history/src/api/history.api.ts
import { dataApi, queryFactory } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import { createLogger } from "@ming/core-log";
import type { HistoryMessage, SaveHistoryRequest } from "./types";
import { parseMessages, unpackDetail } from "./unpack";

const log = createLogger("history/api");

// ---------------------------------------------------------------------------
// 缓存 key
// ---------------------------------------------------------------------------

const HISTORY_LIST_KEY = ["history", "list"] as const;

// ---------------------------------------------------------------------------
// 网络请求（纯 fetcher，只负责请求 + 日志，返回原始 DataApiResponse 透传给 hook 层）
// ---------------------------------------------------------------------------

async function fetchList(): Promise<DataApiResponse<unknown[]>> {
  log.debug("fetch history list");
  return dataApi.get<unknown[]>("/api/history/list/v1", {
    params: { page: 1, page_size: 100 },
  });
}

async function fetchMessages(id: string): Promise<DataApiResponse<unknown>> {
  log.debug("fetch history messages", { id });
  return dataApi.get<unknown>(`/api/history/v1/${id}`);
}

async function saveToServer(
  params: SaveHistoryRequest,
): Promise<DataApiResponse<unknown>> {
  log.debug("save history", { title: params.title });
  return dataApi.post<unknown>("/api/history/save/v1", params);
}

async function addConversation(
  title: string,
): Promise<DataApiResponse<unknown>> {
  log.debug("add conversation", { title });
  return dataApi.post<unknown>("/api/history/save/v1", { title, messages: [] });
}

async function removeFromServer(
  id: string,
): Promise<DataApiResponse<void>> {
  log.debug("remove history", { id });
  return dataApi.delete<void>(`/api/history/v1/${id}`);
}

// ---------------------------------------------------------------------------
// 预配置 hook（使用 queryFactory，mutation 自动失效列表缓存）
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
// 同步调用对象（非 React 上下文使用，不走缓存）
// 内部解包 DataApiResponse，返回干净业务数据
// ---------------------------------------------------------------------------

export const historyStore = {
  list: fetchList,
  messages: async (id: string) =>
    parseMessages(unpackDetail(await fetchMessages(id))?.messages),
  saveMessages: (title: string, messages: HistoryMessage[]) =>
    saveToServer({ title, messages }),
  add: addConversation,
  remove: removeFromServer,
};
