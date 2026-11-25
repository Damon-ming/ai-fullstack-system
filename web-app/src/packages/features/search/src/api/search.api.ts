// web-app/src/packages/features/search/src/api/search.api.ts
import { dataApi } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import type { SearchRequest, SearchResultItem } from "./types";

export function searchHistory(
  request: SearchRequest,
): Promise<DataApiResponse<SearchResultItem[]>> {
  return dataApi.get<SearchResultItem[]>("/api/history/search/v1", {
    params: { keyword: request.keyword, limit: request.limit ?? 20 },
  });
}
