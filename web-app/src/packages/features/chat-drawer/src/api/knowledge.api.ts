import { dataApi } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import type { KnowledgeTreeData } from "./types/knowledge";

/**
 * 获取知识库目录树。
 * 返回原始 DataApiResponse 透传给 hook 层（遵循 monorepo fetcher 模式）。
 */
export async function fetchKnowledgeTree(): Promise<
  DataApiResponse<KnowledgeTreeData>
> {
  return dataApi.get<KnowledgeTreeData>("/api/knowledge/tree/v1");
}
