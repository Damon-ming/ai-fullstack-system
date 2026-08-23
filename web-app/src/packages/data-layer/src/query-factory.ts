// web-app/src/packages/data-layer/src/query-factory.ts
import {
  useQuery,
  useMutation,
  UseQueryOptions,
  UseMutationOptions,
  QueryKey,
} from "@tanstack/react-query";
import type { BizApiResponse, ErrDataResponse } from "@ming/biz-common-net-api";

export class QueryFactory {
  /**
   * 生成Query自定义hook工厂；查询接口用，把fetcher+默认配置收敛在api层
   */
  static genQueryHook<
    TData,
    TError = ErrDataResponse,
    TQueryKey extends QueryKey = QueryKey,
  >(
    fetcher: () => Promise<BizApiResponse<TData>>,
    defaultOptions: Omit<
      UseQueryOptions<
        BizApiResponse<TData>,
        TError,
        BizApiResponse<TData>,
        TQueryKey
      >,
      "queryKey" | "queryFn"
    >,
  ) {
    return (queryKey: TQueryKey, customOptions?: typeof defaultOptions) => {
      return useQuery<
        BizApiResponse<TData>,
        TError,
        BizApiResponse<TData>,
        TQueryKey
      >({
        queryKey,
        queryFn: fetcher,
        ...defaultOptions,
        ...customOptions,
      });
    };
  }

  static genMutationHook<TData, TVariables, TError = ErrDataResponse>(
    fetcher: (vars: TVariables) => Promise<BizApiResponse<TData>>,
    defaultOptions: Omit<
      UseMutationOptions<BizApiResponse<TData>, TError, TVariables>,
      "mutationFn"
    >,
  ) {
    return (
      customOptions?: Omit<
        UseMutationOptions<BizApiResponse<TData>, TError, TVariables>,
        "mutationFn"
      >,
    ) => {
      return useMutation<BizApiResponse<TData>, TError, TVariables>({
        mutationFn: fetcher,
        ...defaultOptions,
        ...customOptions,
      });
    };
  }
}
