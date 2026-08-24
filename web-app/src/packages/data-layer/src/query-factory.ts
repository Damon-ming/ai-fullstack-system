// web-app/src/packages/data-layer/src/query-factory.ts
import {
  useQuery,
  useMutation,
  UseQueryOptions,
  UseMutationOptions,
  QueryKey,
} from "@tanstack/react-query";
import type { DataApiResponse, DataLayerError } from "./types";

export class QueryFactory {
  /**
   * 生成Query自定义hook工厂；查询接口用，把fetcher+默认配置收敛在api层
   */
  static genQueryHook<
    TData,
    TError = DataLayerError,
    TQueryKey extends QueryKey = QueryKey,
  >(
    fetcher: () => Promise<DataApiResponse<TData>>,
    defaultOptions: Omit<
      UseQueryOptions<
        DataApiResponse<TData>,
        TError,
        DataApiResponse<TData>,
        TQueryKey
      >,
      "queryKey" | "queryFn"
    >,
  ) {
    return (queryKey: TQueryKey, customOptions?: typeof defaultOptions) => {
      return useQuery<
        DataApiResponse<TData>,
        TError,
        DataApiResponse<TData>,
        TQueryKey
      >({
        queryKey,
        queryFn: fetcher,
        ...defaultOptions,
        ...customOptions,
      });
    };
  }

  static genMutationHook<TData, TVariables, TError = DataLayerError>(
    fetcher: (vars: TVariables) => Promise<DataApiResponse<TData>>,
    defaultOptions: Omit<
      UseMutationOptions<DataApiResponse<TData>, TError, TVariables>,
      "mutationFn"
    >,
  ) {
    return (
      customOptions?: Omit<
        UseMutationOptions<DataApiResponse<TData>, TError, TVariables>,
        "mutationFn"
      >,
    ) => {
      return useMutation<DataApiResponse<TData>, TError, TVariables>({
        mutationFn: fetcher,
        ...defaultOptions,
        ...customOptions,
      });
    };
  }
}
