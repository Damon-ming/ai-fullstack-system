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
  /**
   * 加密白名单 —— 命中这些前缀的请求不加密（也不尝试解密响应）。
   * 用于密钥交换、公开接口等无加密会话阶段必须调用的端点。
   * 示例：["/api/encryption", "/api/account"]
   */
  encryptionExcludePaths?: string[];
  /** 是否启用全局日志拦截器（打印请求/响应详情，仅 debug 环境使用） */
  enableLogging?: boolean;
}

export interface BaseRequest {
  /** 请求时间戳（毫秒），由拦截器自动注入 */
  timestamp?: number;
  /** 请求随机数（由 generateNonce() 生成的字符串），由拦截器自动注入 */
  nonce?: string;
  /** HMAC-SHA256 签名，由拦截器自动注入 */
  signature?: string;
}

/** 业务层包装后的完整响应 = 底层 http 壳 + 后端业务体 */
export interface BizApiSuccessResponse<T = any> {
  code: number;
  data?: T;
}

/**
 * 前端统一错误响应 —— 由 BizRestClient.requestWrap 构造。
 *
 * 错误信息优先级（统一在 data.error_msg）：
 *   1. 服务端 data.error_msg（原始错误描述）
 *   2. HTTP 状态码文案（服务端未返回结构化 body 时）
 *   3. 客户端兜底文案（网络异常等纯客户端场景，带 CLIENT: 前缀）
 *
 * data 是服务端原始响应体，error_msg 由 requestWrap 统一填充。
 */
export interface BizApiErrorResponse<ErrData = any> {
  code: number;
  data?: ErrData;
}
