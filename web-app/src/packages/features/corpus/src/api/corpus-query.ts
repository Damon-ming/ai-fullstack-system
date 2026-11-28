// corpus/src/api/corpus-query.ts
/**
 * 知识库目录树 Query Hook —— queryFactory 缓存策略配置。
 *
 * 仅配置缓存策略（staleTime、refetchOnWindowFocus），不含业务逻辑。
 * fetcher 本身在 corpus.api.ts 中定义，本层只负责 query 封装。
 */

import { queryFactory } from "@ming/data-layer";
import { fetchCorpusTree } from "./corpus.api";
import type { CorpusTreeData } from "./types/corpus";

/** 知识库目录树缓存 key */
export const CORPUS_TREE_KEY = ["corpus", "tree"] as const;

/** 知识库目录树查询 hook —— 30s 内不重新拉取 */
export const useCorpusQuery =
  queryFactory.createQueryHook<CorpusTreeData>(
    CORPUS_TREE_KEY,
    fetchCorpusTree,
    { staleTime: 30_000, refetchOnWindowFocus: false },
  );
