// web-app/src/packages/features/history/src/api/history-query.ts
/**
 * 历史记录 Query/Mutation Hooks —— 缓存策略配置。
 *
 * 列表用无限滚动分页（useInfiniteQuery），删除用 mutation 自动失效缓存。
 * fetcher 本身在 history.api.ts 中定义，本层只负责 query/mutation 封装。
 */

import type {
  DataApiResponse,
  DataLayerError,
  InfiniteData,
} from "@ming/data-layer";
import { queryFactory, useInfiniteQuery } from "@ming/data-layer";
import { fetchList, removeFromServer } from "./history.api";

// ---------------------------------------------------------------------------
// 缓存 key
// ---------------------------------------------------------------------------

export const HISTORY_LIST_KEY = ["history", "list"] as const;

/** 抽屉列表每页条数 */
export const HISTORY_PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// 预配置 query/mutation hook（仅配置缓存策略，不含业务逻辑）
// ---------------------------------------------------------------------------

/** 列表无限滚动查询 —— 30s 内不重新拉取 */
export const useHistoryListInfiniteQuery = () =>
  useInfiniteQuery<
    DataApiResponse<unknown[]>,
    DataLayerError,
    InfiniteData<DataApiResponse<unknown[]>>,
    typeof HISTORY_LIST_KEY,
    number
  >({
    queryKey: HISTORY_LIST_KEY,
    queryFn: ({ pageParam }) => fetchList(pageParam, HISTORY_PAGE_SIZE),
    initialPageParam: 1,
    // 满页说明可能还有下一页；不足一页即到底
    getNextPageParam: (lastPage, _allPages, _lastPageParam, allPageParams) =>
      (lastPage.data ?? []).length === HISTORY_PAGE_SIZE
        ? (allPageParams.at(-1) ?? 1) + 1
        : undefined,
    staleTime: 30 * 1000,
  });

/** 删除 mutation —— 成功后自动刷新列表 */
export const useRemoveHistoryMutation = queryFactory.createMutationHook<
  void,
  string
>(removeFromServer, { invalidateKeys: [HISTORY_LIST_KEY] });
