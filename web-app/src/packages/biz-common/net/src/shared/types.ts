// src/packages/biz-common/net/src/shared/types.ts
// 公共类型 —— restful 和 sse 模块共用

import type { HttpClientConfig } from "@ming/core-network";
import type {
  SseResponseHeadersInterceptor,
  SseGlobalMessageInterceptor,
} from "../sse/types";

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
  /** 是否启用全局请求/响应加密（默认 false） */
  enableEncryption?: boolean;
  /** 请求签名密钥（与服务端共享）。启用加密时自动启用签名 */
  signatureSecret?: string;
  /** 是否启用全局日志拦截器（打印请求/响应详情，仅 debug 环境使用） */
  enableLogging?: boolean;
  /** 是否启用认证拦截器（注入设备 Token Cookie 头） */
  enableAuth?: boolean;
}

export interface BaseRequest {
  /** 请求时间戳（毫秒），由拦截器自动注入 */
  timestamp?: number;
  /** 请求随机数，由拦截器自动注入 */
  nonce?: string;
  /** HMAC-SHA256 签名，由拦截器自动注入 */
  signature?: string;
}

/** 业务层包装后的完整响应 = 底层 http 壳 + 后端业务体 */
export interface BizApiSuccessResponse<T = any> {
  code: number;
  data?: T;
}

/** 后端标准错误详情 BizApiErrorResponse */
export interface BizApiErrorResponse<ErrData = any> {
  code: number;
  clientData?: ClientErrData; // 只有客户端抛出异常或处理网络错误时存在
  data?: ErrData;
}

/**
 * 客户端专属错误信息（仅客户端码场景存在）
 * UI 层只读 .message 用于展示，不需要分支逻辑 ——
 * 错误来源已由 error.code 唯一确定
 */
export interface ClientErrData {
  message?: string;
}
