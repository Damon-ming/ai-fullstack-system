// web-app/src/packages/data-layer/src/query-factory.ts
import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryOptions,
  UseMutationOptions,
  QueryKey,
} from "@tanstack/react-query";
import type { DataApiResponse, DataLayerError } from "./types";

/**
 * QueryFactory —— 把数据请求 + 缓存策略收敛在 api 层。
 *
 * 实例级方法提供：
 * 1. queryKey 注入能力：api 层在模块级创建预配置 hook，key 由 api 层管理
 * 2. mutation 成功后自动 invalidateQueries 失效关联缓存
 * 3. hook 层不再需要直接调 useQuery/useMutation/useQueryClient
 *
 * 泛型 TData 是业务数据的实际类型，fetcher 返回 DataApiResponse<TData>（透传网络层结构），
 * query/mutation 的 data 字段也是 DataApiResponse<TData>，由 hook 层决定如何解包。
 */
export class QueryFactory {
  /**
   * 创建预配置 query hook。
   * @param queryKey 缓存 key（固定，由 api 层管理）
   * @param fetcher 数据请求函数，返回 DataApiResponse<TData>（透传网络层结构）
   * @param defaultOptions 默认 query 选项
   */
  createQueryHook<TData, TError = DataLayerError, TQueryKey extends QueryKey = QueryKey>(
    queryKey: TQueryKey,
    fetcher: () => Promise<DataApiResponse<TData>>,
    defaultOptions?: Omit<
      UseQueryOptions<DataApiResponse<TData>, TError, DataApiResponse<TData>, TQueryKey>,
      "queryKey" | "queryFn"
    >,
  ) {
    return (customOptions?: typeof defaultOptions) => {
      return useQuery<DataApiResponse<TData>, TError, DataApiResponse<TData>, TQueryKey>({
        queryKey,
        queryFn: fetcher,
        ...defaultOptions,
        ...customOptions,
      });
    };
  }

  /**
   * 创建预配置 mutation hook，支持自动缓存失效。
   * @param fetcher mutation 函数，返回 DataApiResponse<TData>（透传网络层结构）
   * @param options invalidateKeys: mutation 成功后自动失效的 queryKey 列表
   */
  createMutationHook<TData, TVariables, TError = DataLayerError>(
    fetcher: (vars: TVariables) => Promise<DataApiResponse<TData>>,
    options?: {
      invalidateKeys?: QueryKey[];
      defaultOptions?: Omit<
        UseMutationOptions<DataApiResponse<TData>, TError, TVariables>,
        "mutationFn"
      >;
    },
  ) {
    return (
      customOptions?: Omit<
        UseMutationOptions<DataApiResponse<TData>, TError, TVariables>,
        "mutationFn"
      >,
    ) => {
      const queryClient = useQueryClient();
      return useMutation<DataApiResponse<TData>, TError, TVariables>({
        mutationFn: fetcher,
        ...options?.defaultOptions,
        ...customOptions,
        onSuccess: (data, variables, context, mutation) => {
          // 自动失效关联缓存
          if (options?.invalidateKeys) {
            for (const key of options.invalidateKeys) {
              queryClient.invalidateQueries({ queryKey: key });
            }
          }
          // 透传用户注册的 onSuccess
          options?.defaultOptions?.onSuccess?.(data, variables, context, mutation);
          customOptions?.onSuccess?.(data, variables, context, mutation);
        },
      });
    };
  }
}

/** api 层模块级单例，export 给 feature hook 消费 */
export const queryFactory = new QueryFactory();
