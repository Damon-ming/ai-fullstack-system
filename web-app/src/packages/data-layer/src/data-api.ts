// web-app/src/packages/data-layer/src/data-api.ts
import { netClient } from "@ming/biz-common-net-api";
import { unwrapBizResult } from "./unwrapper";
import type {
  DataApiResponse,
  DataLayerRequestConfig,
  DataLayerSseCallbacks,
  DataLayerSseStreamOptions,
  DataLayerSseFinalState,
} from "./types";

/**
 * 纯函数组合工具：对 netClient 进行二次封装，自动进行 unwrap 解包
 *
 * Restful：data-layer 做 [err, res] → resolve/reject 解包
 * SSE：data-layer 只做类型透传，所有公用逻辑（解析/校验/拦截器/错误格式化）下沉到 biz-common-net
 */
export const dataApi = {
  get<T = any, F = any>(
    url: string,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.get<T, F>(url, config));
  },

  post<T = any, F = any>(
    url: string,
    data?: any,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.post<T, F>(url, data, config));
  },

  put<T = any, F = any>(
    url: string,
    data?: any,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.put<T, F>(url, data, config));
  },

  delete<T = any, F = any>(
    url: string,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.delete<T, F>(url, config));
  },

  patch<T = any, F = any>(
    url: string,
    data?: any,
    config?: DataLayerRequestConfig,
  ): Promise<DataApiResponse<T>> {
    return unwrapBizResult<T, F>(netClient.patch<T, F>(url, data, config));
  },

  async sse<T = any>(
    url: string,
    body: unknown,
    callbacks?: DataLayerSseCallbacks<T>,
    opts?: DataLayerSseStreamOptions<T>,
  ): Promise<DataLayerSseFinalState> {
    return netClient.sseStream<T>(url, body, callbacks, opts);
  },
};
