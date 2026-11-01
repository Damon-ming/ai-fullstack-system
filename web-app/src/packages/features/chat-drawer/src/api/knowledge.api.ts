import { dataApi, queryFactory } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import type { KnowledgeTreeData } from "./types/knowledge";

/** 知识库目录树缓存 key */
const KNOWLEDGE_TREE_KEY = ["knowledge", "tree"] as const;

/**
 * 获取知识库目录树。
 * 返回原始 DataApiResponse 透传给 hook 层（遵循 monorepo fetcher 模式）。
 */
export async function fetchKnowledgeTree(): Promise<
  DataApiResponse<KnowledgeTreeData>
> {
  return dataApi.get<KnowledgeTreeData>("/api/knowledge/tree/v1");
}

/** 知识库目录树查询 hook —— 30s 内不重新拉取 */
export const useKnowledgeQuery =
  queryFactory.createQueryHook<KnowledgeTreeData>(
    KNOWLEDGE_TREE_KEY,
    fetchKnowledgeTree,
    { staleTime: 30_000, refetchOnWindowFocus: false },
  );
