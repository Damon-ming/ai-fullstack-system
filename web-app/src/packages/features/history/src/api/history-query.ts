// web-app/src/packages/features/history/src/api/history-query.ts
/**
 * 历史记录 Query/Mutation Hooks —— 缓存策略配置。
 *
 * 列表用无限滚动分页（useInfiniteQuery），删除用 mutation 自动失效缓存。
 * fetcher 本身在 history.api.ts 中定义，本层只负责 query/mutation 封装。
 */

import { useCallback } from "react";
import { useQueryClient , queryFactory, useInfiniteQuery } from "@ming/data-layer";
import type {
  DataApiResponse,
  DataLayerError,
  InfiniteData,
} from "@ming/data-layer";

import {
  fetchList,
  pinOnServer,
  removeFromServer,
  unpinOnServer,
} from "./history.api";

// ---------------------------------------------------------------------------
// 缓存 key
// ---------------------------------------------------------------------------

export const HISTORY_LIST_KEY = ["history", "list"] as const;
export const HISTORY_TURNS_KEY = ["history", "turns"] as const;

export const historyTurnsQueryKey = (conversationId: string) =>
  [...HISTORY_TURNS_KEY, conversationId] as const;

/** 历史详情的缓存读写入口，供 feature hook 编排使用。 */
export function useHistoryTurnsCache() {
  const queryClient = useQueryClient();
  const fetchTurns = useCallback(
    <T,>(conversationId: string, queryFn: () => Promise<T>) =>
      queryClient.query({
        queryKey: historyTurnsQueryKey(conversationId),
        queryFn,
        staleTime: 30 * 1000,
      }),
    [queryClient],
  );
  const invalidateTurns = useCallback(
    () => queryClient.invalidateQueries({ queryKey: HISTORY_TURNS_KEY }),
    [queryClient],
  );
  return { fetchTurns, invalidateTurns };
}

/** 抽屉列表每页条数 */
export const HISTORY_PAGE_SIZE = 20;
/** 会话详情每页轮次数 */
export const HISTORY_TURN_PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// 预配置 query/mutation hook（仅配置缓存策略，不含业务逻辑）
// ---------------------------------------------------------------------------

/** 列表无限滚动查询 —— 30s 内不重新拉取 */
export const useHistoryListInfiniteQuery = () =>
  useInfiniteQuery<
    DataApiResponse<unknown>,
    DataLayerError,
    InfiniteData<DataApiResponse<unknown>>,
    typeof HISTORY_LIST_KEY,
    string | null
  >({
    queryKey: HISTORY_LIST_KEY,
    queryFn: ({ pageParam }) =>
      fetchList(pageParam ?? undefined, HISTORY_PAGE_SIZE),
    initialPageParam: null,
    getNextPageParam: (lastPage) => {
      const data = lastPage.data as
        | { hasMore?: boolean; nextCursor?: string | null }
        | undefined;
      return data?.hasMore && data.nextCursor ? data.nextCursor : undefined;
    },
    staleTime: 30 * 1000,
  });

/** 删除 mutation —— 成功后自动刷新列表 */
export const useRemoveHistoryMutation = queryFactory.createMutationHook<
  void,
  string
>(removeFromServer, { invalidateKeys: [HISTORY_LIST_KEY] });

export const usePinHistoryMutation = queryFactory.createMutationHook<
  unknown,
  string
>(pinOnServer, {
  invalidateKeys: [HISTORY_LIST_KEY],
});

export const useUnpinHistoryMutation = queryFactory.createMutationHook<
  unknown,
  string
>(unpinOnServer, {
  invalidateKeys: [HISTORY_LIST_KEY],
});
