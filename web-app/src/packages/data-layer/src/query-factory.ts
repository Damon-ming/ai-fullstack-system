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
 * 静态方法（genQueryHook/genMutationHook）保持向后兼容，供已有 chat-chatroom 使用。
 *
 * 实例级方法新增 cacheKey 注入能力：api 层在模块级创建单例工厂，
 * mutation 成功后自动调用 invalidateQueries 失效关联 query 的缓存，
 * hook 层不再需要直接调 useQuery/useMutation/useQueryClient。
 *
 * 实例方法的泛型 TData/TVariables 是 fetcher 的【实际返回类型】，
 * 不做 DataApiResponse 包装 —— api 层 fetcher 内部自行解包。
 */
export class QueryFactory {
  // ---------------------------------------------------------------------------
  // 静态方法（向后兼容，无 QueryClient 访问能力）
  // ---------------------------------------------------------------------------

  /** @deprecated 优先使用实例级方法以支持自动缓存失效 */
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

  /** @deprecated 优先使用实例级方法以支持自动缓存失效 */
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

  // ---------------------------------------------------------------------------
  // 实例级方法（支持自动缓存失效，泛型为实际返回类型）
  // ---------------------------------------------------------------------------

  /**
   * 创建预配置 query hook。
   * @param queryKey 缓存 key（固定，由 api 层管理）
   * @param fetcher 数据请求函数，返回实际业务数据（非 DataApiResponse 包装）
   * @param defaultOptions 默认 query 选项
   */
  createQueryHook<TData, TError = DataLayerError, TQueryKey extends QueryKey = QueryKey>(
    queryKey: TQueryKey,
    fetcher: () => Promise<TData>,
    defaultOptions?: Omit<
      UseQueryOptions<TData, TError, TData, TQueryKey>,
      "queryKey" | "queryFn"
    >,
  ) {
    return (customOptions?: typeof defaultOptions) => {
      return useQuery<TData, TError, TData, TQueryKey>({
        queryKey,
        queryFn: fetcher,
        ...defaultOptions,
        ...customOptions,
      });
    };
  }

  /**
   * 创建预配置 mutation hook，支持自动缓存失效。
   * @param fetcher mutation 函数，参数为 TVariables，返回实际数据
   * @param options invalidateKeys: mutation 成功后自动失效的 queryKey 列表
   */
  createMutationHook<TData, TVariables, TError = DataLayerError>(
    fetcher: (vars: TVariables) => Promise<TData>,
    options?: {
      invalidateKeys?: QueryKey[];
      defaultOptions?: Omit<
        UseMutationOptions<TData, TError, TVariables>,
        "mutationFn"
      >;
    },
  ) {
    return (
      customOptions?: Omit<
        UseMutationOptions<TData, TError, TVariables>,
        "mutationFn"
      >,
    ) => {
      const queryClient = useQueryClient();
      return useMutation<TData, TError, TVariables>({
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
