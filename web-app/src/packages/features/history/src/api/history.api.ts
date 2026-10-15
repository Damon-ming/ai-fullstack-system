// web-app/src/packages/features/history/src/api/history.api.ts
import { dataApi, queryFactory } from "@ming/data-layer";
import type { HistoryItem, HistoryMessage } from "./types/response";

/**
 * 对话历史 API —— 从 localStorage 迁移到服务端 DB。
 *
 * 职责：数据请求 + 缓存策略，全部收敛在此 api 层。
 * 网络路径：history.api → dataApi (data-layer) → netClient (biz-common-net) → 后端
 *
 * 本模块使用 queryFactory 单例创建预配置 hook，
 * mutation 成功后自动失效列表缓存，hook 层无需接触 useQuery/useMutation/useQueryClient。
 */

// 缓存 key —— 列表/详情共享同一 key 空间
const HISTORY_LIST_KEY = ["history", "list"] as const;

/** 解析服务端时间戳（ISO 字符串或 epoch）→ epoch ms。 */
function parseTimestamp(item: any): number {
  const raw = item.createdAt || item.created_at;
  return raw ? new Date(raw).getTime() : Date.now();
}

/** 服务端 HistoryListItem → 前端 HistoryItem（不含 messages）。 */
function listItemToHistoryItem(item: any): HistoryItem {
  return {
    id: item.id,
    title: item.title,
    meta: item.updatedAt || item.updated_at || "",
    createdAt: parseTimestamp(item),
    messages: [],
  };
}

/** 服务端 HistoryDetailData → 前端 HistoryItem（含 messages）。 */
function detailToHistoryItem(detail: any): HistoryItem {
  const messages: HistoryMessage[] = (detail.messages || []).map((m: any) => ({
    id: m.id,
    text: m.text,
    role: m.role as "user" | "assistant",
  }));
  return {
    id: detail.id,
    title: detail.title,
    meta: detail.updatedAt || detail.updated_at || "",
    createdAt: parseTimestamp(detail),
    messages,
  };
}

// ---------------------------------------------------------------------------
// 网络请求函数（纯 fetcher，不含 hook）
// ---------------------------------------------------------------------------

async function fetchList(): Promise<HistoryItem[]> {
  const res = await dataApi.get("/api/history/list", {
    params: { page: 1, page_size: 100 },
  });
  const items: any[] = res.data?.items || [];
  return items.map(listItemToHistoryItem);
}

async function fetchMessages(id: string): Promise<HistoryMessage[]> {
  const res = await dataApi.get(`/api/history/${id}`);
  const detail = res.data?.conversation || res.data;
  return (detail?.messages || []).map((m: any) => ({
    id: m.id,
    text: m.text,
    role: m.role as "user" | "assistant",
  }));
}

async function saveToServer(params: {
  title: string;
  messages: HistoryMessage[];
}): Promise<HistoryItem> {
  const res = await dataApi.post("/api/history/save", params);
  return detailToHistoryItem(res.data.conversation);
}

async function addConversation(title: string): Promise<HistoryItem> {
  const res = await dataApi.post("/api/history/save", { title, messages: [] });
  return detailToHistoryItem(res.data.conversation);
}

async function removeFromServer(id: string): Promise<void> {
  await dataApi.delete(`/api/history/${id}`);
}

// ---------------------------------------------------------------------------
// 预配置 hook（使用 queryFactory，mutation 自动失效列表缓存）
// ---------------------------------------------------------------------------

/** 列表查询 hook —— 30s 内不重新拉取 */
export const useHistoryListQuery = queryFactory.createQueryHook<HistoryItem[]>(
  HISTORY_LIST_KEY,
  fetchList,
  { staleTime: 30 * 1000 },
);

/** 保存 mutation —— 成功后自动刷新列表 */
export const useSaveHistoryMutation = queryFactory.createMutationHook<
  HistoryItem,
  { title: string; messages: HistoryMessage[] }
>(saveToServer, { invalidateKeys: [HISTORY_LIST_KEY] });

/** 删除 mutation —— 成功后自动刷新列表 */
export const useRemoveHistoryMutation = queryFactory.createMutationHook<void, string>(
  removeFromServer,
  { invalidateKeys: [HISTORY_LIST_KEY] },
);

// ---------------------------------------------------------------------------
// 同步调用对象（非 React 上下文使用，不走缓存）
// ---------------------------------------------------------------------------

export const historyStore = {
  list: fetchList,
  messages: fetchMessages,
  saveMessages: (title: string, messages: HistoryMessage[]) =>
    saveToServer({ title, messages }),
  add: addConversation,
  remove: removeFromServer,
};
