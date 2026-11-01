// web-app/src/packages/features/chat-drawer/src/api/knowledge-query.ts
/**
 * 知识库目录树 Query Hook —— queryFactory 缓存策略配置。
 *
 * 仅配置缓存策略（staleTime、refetchOnWindowFocus），不含业务逻辑。
 * fetcher 本身在 knowledge.api.ts 中定义，本层只负责 query 封装。
 */

import { queryFactory } from "@ming/data-layer";
import { fetchKnowledgeTree } from "./knowledge.api";
import type { KnowledgeTreeData } from "./types/knowledge";

/** 知识库目录树缓存 key */
export const KNOWLEDGE_TREE_KEY = ["knowledge", "tree"] as const;

/** 知识库目录树查询 hook —— 30s 内不重新拉取 */
export const useKnowledgeQuery =
  queryFactory.createQueryHook<KnowledgeTreeData>(
    KNOWLEDGE_TREE_KEY,
    fetchKnowledgeTree,
    { staleTime: 30_000, refetchOnWindowFocus: false },
  );
