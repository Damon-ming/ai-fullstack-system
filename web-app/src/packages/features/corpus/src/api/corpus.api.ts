// corpus/src/api/corpus.api.ts
import { dataApi } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import type { CorpusTreeData } from "./types/corpus";

/**
 * 获取知识库目录树。
 * 返回原始 DataApiResponse 透传给 hook 层（遵循 monorepo fetcher 模式）。
 */
export async function fetchCorpusTree(): Promise<
  DataApiResponse<CorpusTreeData>
> {
  return dataApi.get<CorpusTreeData>("/api/corpus/tree/v1");
}
