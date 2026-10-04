// web-app/src/packages/data-layer/src/types.ts
import type {
  UseQueryOptions,
  UseMutationOptions,
} from "@tanstack/react-query";

/** 数据层成功响应。网络层的 BizApiSuccessResponse 不直接暴露给上层业务。 */
export interface DataApiResponse<T = unknown> {
  code: number;
  data?: T;
}

/** 数据层错误。结构与 biz-common-net 的 BizApiErrorResponse 对齐，供 query/mutation 使用。 */
export interface DataLayerError<ErrData = unknown> {
  code: number;
  clientData?: {
    message?: string;
  };
  data?: ErrData;
}

/**
 * 单次数据层请求配置。字段与网络实现兼容，但不暴露网络层类型。
 */
export interface DataLayerRequestConfig {
  params?: Record<string, unknown>;
  headers?: Record<string, string>;
  data?: unknown;
  timeout?: number;
  axiosConfig?: Record<string, unknown>;
}

export interface DataLayerRequestMeta {
  event?: string;
  id?: string;
  retry?: number;
}

export interface DataLayerSseRequestOptions {
  signal?: AbortSignal;
  extraHeaders?: Record<string, string>;
}

export interface DataLayerSseStreamOptions<
  T = unknown,
> extends DataLayerSseRequestOptions {
  parse?: ((raw: string) => T) | false;
  validateMessage?: (payload: T) => {
    isError: boolean;
    error?: DataLayerError;
  };
  messageInterceptors?:
    | DataLayerSseMessageInterceptor<T>
    | DataLayerSseMessageInterceptor<T>[];
  onResponseHeaders?: (response: Response) => void | Promise<void>;
}

export interface DataLayerSseMessageInterceptor<T = unknown> {
  onFulfilled?: (payload: T, meta?: DataLayerRequestMeta) => T | Promise<T>;
  onRejected?: (error: unknown) => unknown;
}

export interface DataLayerSseCallbacks<T = unknown> {
  onMessage?: (payload: T, meta?: DataLayerRequestMeta) => void;
  onMessageError?: (error: unknown, rawPayload: string) => void;
  onError?: (error: DataLayerError) => void;
  onComplete?: () => void;
  onStatus?: (status: DataLayerSseStatus) => void;
}

export type DataLayerSseStatus =
  | "connected"
  | "message"
  | "heartbeat"
  | "retry-updated"
  | "complete"
  | "aborted"
  | "transport-error"
  | "parse-error"
  | "business-error";

export type DataLayerSseFinalState =
  | { status: "complete" }
  | { status: "error"; error: DataLayerError };

// UseQueryOptions<
//   TQueryFnData,    // ① queryFn 返回的数据类型
//   TError,          // ② 错误类型
//   TData,           // ③ select 处理后的数据类型
//   TQueryKey        // ④ queryKey 的类型
// >
// TQueryKey = queryKey 的类型（可省略）。

// TQueryFnData
// queryFn 返回的数据类型（原始数据）
// const query = useQuery({
//   queryFn: () => fetch("/api/user").then(r => r.json()),  // 返回 User
//   ...
// });
// TQueryFnData = User

// TData
// select 处理后的数据类型。
// const query = useQuery({
//   queryFn: () => fetch("/api/user").then(r => r.json()),  // User
//   select: (user) => user.name,                             // string
// });
// TQueryFnData = User
// TData = string
// 不传 select 时，TData = TQueryFnData。
// 传 select 时，TData 是 select 的返回类型。

// TQueryKey
// queryKey 的类型。
// const query = useQuery({
//   queryKey: ["user", userId] as const,   // 类型是 readonly ["user", string]
//   ...
// });
// TQueryKey = readonly ["user", string]

/**
 * TanStack Query 配置的类型别名封装
 * 解耦对 TanStack Query 具体泛型复杂度的依赖
 */

// useQuery({
//   queryKey: [...],   // 缓存键
//   queryFn: () => ..., // 怎么拿数据
// });

// const query = useQuery({
//   queryKey: ["user", 1],
//   queryFn: () => fetch("/api/user/1").then(r => r.json()),
//        ↑ 这就是 queryFn
// });
export type BaseQueryOptions<TData = any, TError = DataLayerError> = Omit<
  UseQueryOptions<DataApiResponse<TData>, TError, DataApiResponse<TData>>,
  "queryKey" | "queryFn"
>;

// TVariables 是什么
// mutationFn 的参数类型（mutation 提交的变量类型）。
// const mutation = useMutation({
//   mutationFn: (vars: { id: number; name: string }) => updateUser(vars),
//           ↑ 这就是 TVariables
// });
// mutation.mutate({ id: 1, name: "Alice" });   // 传参
// void 表示"没有参数"。

// 有些 mutation 不需要参数（如"刷新缓存"）。

// 有些需要参数（如"更新用户"）。

// 默认 void 让不需要参数的 mutation 不用写泛型：
// mutationFn 是什么
// useMutation 的必填参数，类比 queryFn。
// useMutation({
//   mutationFn: (vars) => ...,   // ← 怎么提交数据
// });
// queryFn vs mutationFn
// 用于：	useQuery（读）	useMutation（写）
// 接收参数：	不接收（或上下文）	接收变量
// 典型场景：	GET 列表/详情	POST/PUT/DELETE
// 缓存：	有缓存	无缓存

// const mutation = useMutation({
//   mutationFn: (vars: { id: number; name: string }) =>
//     fetch(`/api/user/${vars.id}`, {
//       method: "PUT",
//       body: JSON.stringify({ name: vars.name }),
//     }).then(r => r.json()),
// });
// mutationFn 接收 { id, name }。

// mutate 调用时传 { id, name }。

// TVariables 就是 { id: number; name: string }。

// mutation.mutate({ id: 1, name: "Alice" }); // 提交数据

export type BaseMutationOptions<
  TData = any,
  TVariables = void,
  TError = DataLayerError,
> = Omit<
  UseMutationOptions<DataApiResponse<TData>, TError, TVariables>,
  "mutationFn"
>;
