// web-app/src/packages/data-layer/src/data-api.ts
import {
  netClient,
  type BizRequestConfig,
  type BizApiResponse,
  type SseFinalState,
  SseStreamCallbacks,
  SseStreamOptions
} from "@ming/biz-common-net-api";
import { unwrapBizResult } from "./unwrapper";

/**
 * 纯函数组合工具：对 netClient 进行二次封装，自动进行 unwrap 解包
 */
export const dataApi = {
  get<T = any, F = any>(
    url: string,
    config?: BizRequestConfig,
  ): Promise<BizApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.get<T, F>(url, config));
  },

  post<T = any, F = any>(
    url: string,
    data?: any,
    config?: BizRequestConfig,
  ): Promise<BizApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.post<T, F>(url, data, config));
  },

  put<T = any, F = any>(
    url: string,
    data?: any,
    config?: BizRequestConfig,
  ): Promise<BizApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.put<T, F>(url, data, config));
  },

  delete<T = any, F = any>(
    url: string,
    config?: BizRequestConfig,
  ): Promise<BizApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.delete<T, F>(url, config));
  },

  patch<T = any, F = any>(
    url: string,
    data?: any,
    config?: BizRequestConfig,
  ): Promise<BizApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.patch<T, F>(url, data, config));
  },

  /**
   * SSE 流式请求 — data-layer 只做类型透传
   * 所有公用业务逻辑（解析/校验/消息拦截器/错误格式化/callbacks）
   * 全部下沉到 biz-common-net 的 sseStream
   */
  async sse<T = any>(
    url: string,
    body: unknown,
    callbacks?: SseStreamCallbacks<T>,
    opts?: SseStreamOptions<T>,
  ): Promise<SseFinalState> {
    return netClient.sseStream<T>(url, body, callbacks ?? {}, opts ?? {});
  },
};
