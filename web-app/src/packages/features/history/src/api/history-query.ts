// web-app/src/packages/features/history/src/api/history-query.ts
/**
 * 历史记录 Query/Mutation Hooks —— queryFactory 缓存策略配置。
 *
 * 仅配置缓存策略（staleTime、invalidateKeys），不含业务逻辑。
 * fetcher 本身在 history.api.ts 中定义，本层只负责 query/mutation 封装。
 */

import { queryFactory } from "@ming/data-layer";
import { fetchList, removeFromServer } from "./history.api";

// ---------------------------------------------------------------------------
// 缓存 key
// ---------------------------------------------------------------------------

export const HISTORY_LIST_KEY = ["history", "list"] as const;

// ---------------------------------------------------------------------------
// 预配置 query/mutation hook（仅配置缓存策略，不含业务逻辑）
// ---------------------------------------------------------------------------

/** 列表查询 hook —— 30s 内不重新拉取 */
export const useHistoryListQuery = queryFactory.createQueryHook<unknown[]>(
  HISTORY_LIST_KEY,
  fetchList,
  { staleTime: 30 * 1000 },
);

/** 删除 mutation —— 成功后自动刷新列表 */
export const useRemoveHistoryMutation = queryFactory.createMutationHook<
  void,
  string
>(removeFromServer, { invalidateKeys: [HISTORY_LIST_KEY] });
