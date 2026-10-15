// src/packages/data-layer/src/index.ts

export { unwrapBizResult } from "./unwrapper";
export { dataApi } from "./data-api";
export { QueryFactory, queryFactory } from "./query-factory";
export { DataProvider } from "./provider";

// TanStack Query 原语 —— 重导出供 feature 层使用，保持 data-layer 作为唯一网络抽象边界
export {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

export type {
  DataLayerRequestConfig,
  DataApiResponse,
  DataLayerError,
  DataLayerRequestMeta,
  DataLayerSseRequestOptions,
  DataLayerSseStreamOptions,
  DataLayerSseMessageInterceptor,
  DataLayerSseCallbacks,
  DataLayerSseFinalState,
  DataLayerSseStatus,
  BaseQueryOptions,
  BaseMutationOptions,
} from "./types";
