// web-app/src/packages/data-layer/src/data-api.ts
import {
  netClient,
  type BizRequestConfig,
  type SseStreamCallbacks,
  type SseStreamOptions,
} from "@ming/biz-common-net-api";
import { unwrapBizResult } from "./unwrapper";
import type { DataApiResponse } from "./types";
import type {
  DataLayerRequestConfig,
  DataLayerSseCallbacks,
  DataLayerSseStreamOptions,
  DataLayerSseFinalState,
} from "./types";

const toBizRequestConfig = (config?: DataLayerRequestConfig): BizRequestConfig | undefined =>
  config as BizRequestConfig | undefined;

const toBizSseCallbacks = <T,>(callbacks?: DataLayerSseCallbacks<T>): SseStreamCallbacks<T> =>
  callbacks as SseStreamCallbacks<T>;

const toBizSseOptions = <T,>(opts?: DataLayerSseStreamOptions<T>): SseStreamOptions<T> =>
  opts as SseStreamOptions<T>;

/**
 * 纯函数组合工具：对 netClient 进行二次封装，自动进行 unwrap 解包
 */
export const dataApi = {
  get<T = any, F = any>(
    url: string,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.get<T, F>(url, toBizRequestConfig(config)));
  },

  post<T = any, F = any>(
    url: string,
    data?: any,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.post<T, F>(url, data, toBizRequestConfig(config)));
  },

  put<T = any, F = any>(
    url: string,
    data?: any,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.put<T, F>(url, data, toBizRequestConfig(config)));
  },

  delete<T = any, F = any>(
    url: string,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.delete<T, F>(url, toBizRequestConfig(config)));
  },

  patch<T = any, F = any>(
    url: string,
    data?: any,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.patch<T, F>(url, data, toBizRequestConfig(config)));
  },

  /**
   * SSE 流式请求 — data-layer 只做类型透传
   * 所有公用业务逻辑（解析/校验/消息拦截器/错误格式化/callbacks）
   * 全部下沉到 biz-common-net 的 sseStream
   */
  async sse<T = any>(
    url: string,
    body: unknown,
    callbacks?: DataLayerSseCallbacks<T>,
    opts?: DataLayerSseStreamOptions<T>,
  ): Promise<DataLayerSseFinalState> {
    return netClient.sseStream<T>(url, body, toBizSseCallbacks(callbacks), toBizSseOptions(opts)).then(
      (result) => result as DataLayerSseFinalState,
    );
  },
};
