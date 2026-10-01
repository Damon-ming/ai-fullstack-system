// web-app/src/packages/data-layer/src/types.ts
import type { UseQueryOptions, UseMutationOptions } from '@tanstack/react-query'

/** 数据层成功响应。网络层的 BizApiSuccessResponse 不直接暴露给上层业务。 */
export interface DataApiResponse<T = unknown> {
  code: number
  data?: T
}

/** 数据层错误。保留业务错误码和客户端错误详情，供 query/mutation 使用。 */
export interface DataLayerError<ErrData = unknown> {
  code: number
  clientData?: {
    message?: string
  }
  data?: ErrData
}

/** 
 * 单次数据层请求配置。字段与网络实现兼容，但不暴露网络层类型。
 */
export interface DataLayerRequestConfig {
  params?: Record<string, unknown>
  headers?: Record<string, string>
  data?: unknown
  timeout?: number
  axiosConfig?: Record<string, unknown>
}

export interface DataLayerRequestMeta {
  event?: string
  id?: string
}

export interface DataLayerSseRequestOptions {
  signal?: AbortSignal
  extraHeaders?: Record<string, string>
}

export interface DataLayerSseStreamOptions<T = unknown> extends DataLayerSseRequestOptions {
  parse?: ((raw: string) => T) | false
  validateMessage?: (payload: T) => {
    isError: boolean
    error?: DataLayerError
  }
  messageInterceptors?: DataLayerSseMessageInterceptor<T> | DataLayerSseMessageInterceptor<T>[]
  onResponseHeaders?: (response: Response) => void | Promise<void>
}

export interface DataLayerSseMessageInterceptor<T = unknown> {
  onFulfilled?: (payload: T, meta?: DataLayerRequestMeta) => T | Promise<T>
  onRejected?: (error: unknown) => unknown
}

export interface DataLayerSseCallbacks<T = unknown> {
  onMessage?: (payload: T, meta?: DataLayerRequestMeta) => void
  onMessageError?: (error: unknown, rawPayload: string) => void
  onError?: (error: DataLayerError) => void
  onComplete?: () => void
  onStatus?: (status: DataLayerSseStatus) => void
}

export type DataLayerSseStatus =
  | "connected"
  | "message"
  | "heartbeat"
  | "complete"
  | "aborted"
  | "transport-error"
  | "parse-error"
  | "business-error"

export type DataLayerSseFinalState =
  | { status: "complete" }
  | { status: "error"; error: DataLayerError }

/** 
 * TanStack Query 配置的类型别名封装
 * 解耦对 TanStack Query 具体泛型复杂度的依赖
 */
export type BaseQueryOptions<TData = any, TError = DataLayerError> = 
  Omit<UseQueryOptions<DataApiResponse<TData>, TError, DataApiResponse<TData>>, 'queryKey' | 'queryFn'>

export type BaseMutationOptions<TData = any, TVariables = void, TError = DataLayerError> = 
  Omit<UseMutationOptions<DataApiResponse<TData>, TError, TVariables>, 'mutationFn'>
