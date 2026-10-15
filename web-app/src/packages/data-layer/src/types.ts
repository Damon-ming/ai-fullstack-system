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
  /** 用于取消（中止）正在进行的请求，透传至 axios signal */
  signal?: AbortSignal;
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

// ---------------------------------------------------------------------------
// TanStack Query 选项别名
//
// UseQueryOptions 四个泛型：
//   TQueryFnData — queryFn 返回值类型（此处为 DataApiResponse<TData>）
//   TError        — 错误类型（DataLayerError）
//   TData         — select 处理后类型（不传 select 则等同于 TQueryFnData）
//   TQueryKey     — queryKey 类型
//
// UseMutationOptions 三个泛型：
//   TData       — mutationFn 返回值类型（DataApiResponse<TData>）
//   TError      — 错误类型（DataLayerError）
//   TVariables  — mutate 参数类型
// ---------------------------------------------------------------------------

export type BaseQueryOptions<TData = any, TError = DataLayerError> = Omit<
  UseQueryOptions<DataApiResponse<TData>, TError, DataApiResponse<TData>>,
  "queryKey" | "queryFn"
>;

export type BaseMutationOptions<
  TData = any,
  TVariables = void,
  TError = DataLayerError,
> = Omit<
  UseMutationOptions<DataApiResponse<TData>, TError, TVariables>,
  "mutationFn"
>;
