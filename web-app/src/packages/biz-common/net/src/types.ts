// src/packages/biz-common-net/src/types.ts

import { HttpClientConfig, RequestConfig } from "@ming/core-network";
import type { InterceptorConfig, NormalizedRequest } from "@ming/core-network";

/**
 * 单次业务请求配置 (BizRequestConfig)
 * 复用 core 的 RequestConfig (剔除 url 和 method)，并补充/覆盖业务特有配置
 * 后半部分 { timeout?: number }：补充的一个新字段
 */
export type BizRequestConfig = Omit<RequestConfig, "url" | "method"> & {
  /** 单次请求超时时间（单位：毫秒） */
  timeout?: number;
};

export interface BaseRequest {
  requestId?: string;
  // todo
  requestedAt?: number;
}

/**
 * 全局启动/初始化网络配置 (BizHttpClientConfig)
 * 继承 core 的 HttpClientConfig，并定义业务启动层需要的字段
 */
export interface BizHttpClientConfig extends HttpClientConfig {
  /** 默认请求超时时间，默认 10000ms */
  timeout?: number;
  /** SSE 全局响应头拦截器（支持单个或数组） */
  sseResponseHeadersInterceptors?:
    | SseResponseHeadersInterceptor
    | SseResponseHeadersInterceptor[];
  /** SSE 全局消息拦截器（支持单个或数组） */
  sseMessageInterceptors?:
    | SseGlobalMessageInterceptor
    | SseGlobalMessageInterceptor[];
}

/** 后端标准错误详情 ErrDataResponse */
export interface ErrDataResponse<ErrData = any> {
  bizCode: number;
  clientErrData?: ClientErrData; // 只有客户端抛出异常或处理网络错误时存在
  errData?: ErrData;
}

/** 业务层包装后的完整响应 = 底层http壳 + 后端业务体 */
export interface BizApiResponse<T = any> {
  bizCode: number;
  data?: T;
}

/** 客户端专属错误信息（仅网络/配置/HTTP非200时存在） */
export interface ClientErrData {
  message?: string;
  httpCode?: number; // 携带原始HTTP状态码 301/404/500
  rawServerRes?: Record<string, any>; // 后端返回原生错误体 {code,message,path...}
}

/** 请求回调集合 */
export interface BizRequestCallbacks<T = any, F = any> {
  onSuccess?: (res: BizApiResponse<T>) => void;
  onFailed?: (error: ErrDataResponse<F>) => void;
  onFinally?: () => void;
}

/**
 * 核心：元组返回格式 [ErrDataResponse | null, BizApiResponse | null]
 * 失败：[ErrDataResponse, null]
 * 成功：[null, BizApiResponse]
 */
export type BizResult<T = any, F = any> = [
  ErrDataResponse<F> | null,
  BizApiResponse<T> | null,
];

/**
 * 通用SSE请求选项
 */
export interface SseRequestOptions {
  /** 取消信号，用于中断SSE长连接 */
  signal?: AbortSignal;
  /** 请求头扩展，可覆盖/追加headers */
  extraHeaders?: Record<string, string>;
}

/**
 * SSE流式回调
 * rawData：剥离 `data: ` 之后的原始字符串，上层自行JSON.parse
 */
export type SseOnMessage = (
  rawData: string,
  meta?: { event?: string; id?: string },
) => void;

/**
 * SSE 消息级拦截器
 * 每条消息解析后、抛给 onMessage 之前经过此链
 * 对齐普通请求的"响应拦截器"，但作用于单条消息而非完整响应
 */
export interface SseMessageInterceptor<T = any> {
  onFulfilled?: (
    payload: T,
    meta?: { event?: string; id?: string },
  ) => T | Promise<T>;
  onRejected?: (error: any) => any;
}

/**
 * SSE 流式请求选项（biz-common-net 业务层）
 * 继承基础 SseRequestOptions，扩展业务能力
 */
export interface SseStreamOptions<T = any> extends SseRequestOptions {
  /** 单次请求拦截器（仅 request；加载顺序：全局 → 单次，与 restful 一致） */
  interceptors?: {
    request?:
      | InterceptorConfig<NormalizedRequest>
      | InterceptorConfig<NormalizedRequest>[];
  };
  /** 消息解析函数，默认 JSON.parse；传 false 则给原始字符串 */
  parse?: ((raw: string) => T) | false;
  /**
   * 业务消息校验（可选）：判断解析后的消息是否为业务错误
   * 对齐 restful 的 bizCode 解析；不配置则所有消息都走 onMessage
   */
  validateMessage?: (payload: T) => {
    isError: boolean;
    error?: ErrDataResponse;
  };
  /** 消息级拦截器链（可选） */
  messageInterceptors?: SseMessageInterceptor<T> | SseMessageInterceptor<T>[];
  /**
   * 【新增】HTTP 响应头阶段回调
   * 在拿到 fetch Response 后、读取流之前调用，可用于读取 X-Request-Id 等特定 header
   */
  onResponseHeaders?: (res: Response) => void | Promise<void>;
}

/**
 * SSE 流式回调（对齐 BizRequestCallbacks）
 */
export interface SseStreamCallbacks<T = any> {
  onMessage?: (payload: T, meta?: { event?: string; id?: string }) => void;
  onMessageError?: (error: unknown, rawPayload: string) => void;
  onError?: (err: ErrDataResponse) => void;
  onComplete?: () => void;
  onStatus?: (status: SseStreamStatus) => void;
}

export type SseStreamStatus =
  | "connected"
  | "message"
  | "heartbeat"
  | "complete"
  | "aborted"
  | "transport-error"
  | "parse-error"
  | "business-error";

/**
 * SSE 全局响应头拦截器
 * 在拿到 fetch Response 后、读取流之前执行
 * 用途：读取 X-Request-Id、检测 token 过期、统一响应日志等
 */
export interface SseResponseHeadersInterceptor {
  onFulfilled?: (res: Response) => void | Promise<void>;
  onRejected?: (error: any) => void;
}

/**
 * SSE 全局消息拦截器（无泛型，适用于所有类型消息）
 * 每条消息解析后、单次 messageInterceptors 之前执行
 */
export interface SseGlobalMessageInterceptor {
  onFulfilled?: (
    payload: any,
    meta?: { event?: string; id?: string },
  ) => any | Promise<any>;
  /** 返回 false 表示吞掉这条消息，不再向下传递 */
  onRejected?: (error: any) => any;
}

/**
 * SSE 流最终状态
 * await sseStream() 后可类型安全地判断流是正常结束还是异常结束
 * - complete：服务端正常关闭连接，所有消息已处理完
 * - error：连接建立失败 / HTTP 非 2xx / 网络异常 / 请求取消
 */
export type SseFinalState =
  | { status: "complete" }
  | { status: "error"; error: ErrDataResponse };
