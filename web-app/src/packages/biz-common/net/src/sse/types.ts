// src/packages/biz-common/net/src/sse/types.ts
// SSE 相关类型 —— 仅 SSE 模块使用

import type { SseRequestOptions } from "@ming/core-network";
import type { BizApiErrorResponse } from "../shared/types";

/**
 * SSE 消息级拦截器
 * 每条消息解析后、抛给 onMessage 之前经过此链
 * 对齐普通请求的"响应拦截器"，但作用于单条消息而非完整响应
 */
export interface SseMessageInterceptor<T = any> {
  onFulfilled?: (
    payload: T,
    meta?: { event?: string; id?: string; retry?: number },
  ) => T | Promise<T>;
  onRejected?: (error: any) => any;
}

/**
 * SSE 流式请求选项（biz-common-net 业务层）
 * 继承基础 SseRequestOptions，扩展业务能力
 */
export interface SseStreamOptions<T = any> extends SseRequestOptions {
  /** 消息解析函数，默认 JSON.parse；传 false 则给原始字符串 */
  parse?: ((raw: string) => T) | false;
  /**
   * 业务消息校验（可选）：判断解析后的消息是否为业务错误
   * 对齐 restful 的 code 解析；不配置则所有消息都走 onMessage
   */
  validateMessage?: (payload: T) => {
    isError: boolean;
    error?: BizApiErrorResponse;
  };
  /** 消息级拦截器链（可选） */
  messageInterceptors?: SseMessageInterceptor<T> | SseMessageInterceptor<T>[];
  /**
   * HTTP 响应头阶段回调
   * 在拿到 fetch Response 后、读取流之前调用，可用于读取 X-Request-Id 等特定 header
   */
  onResponseHeaders?: (res: Response) => void | Promise<void>;
}

/**
 * SSE 流式回调（对齐 BizRequestCallbacks）
 */
export interface SseStreamCallbacks<T = any> {
  onMessage?: (
    payload: T,
    meta?: { event?: string; id?: string; retry?: number },
  ) => void;
  onMessageError?: (error: unknown, rawPayload: string) => void;
  onError?: (err: BizApiErrorResponse) => void;
  onComplete?: () => void;
  onStatus?: (status: SseStreamStatus) => void;
}

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
    meta?: { event?: string; id?: string; retry?: number },
  ) => any | Promise<any>;
  /** 返回 false 表示吞掉这条消息，不再向下传递 */
  onRejected?: (error: any) => any;
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
 * SSE 流最终状态
 * await sseStream() 后可类型安全地判断流是正常结束还是异常结束
 * - complete：服务端正常关闭连接，所有消息已处理完
 * - error：连接建立失败 / HTTP 非 2xx / 网络异常 / 请求取消
 */
export type SseFinalState =
  | { status: "complete" }
  | { status: "error"; error: BizApiErrorResponse };
