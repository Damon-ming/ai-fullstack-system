// web-app/src/packages/biz-common/net-api/src/net-client.ts
import { BizHttp } from "@ming/biz-common-net";
import type {
  BizHttpClientConfig,
  BizResult,
  BizRequestConfig,
  BizRequestCallbacks,
  SseStreamCallbacks,
  SseStreamOptions,
  SseFinalState,
} from "@ming/biz-common-net";
import type { INetClient } from "./interface";

/**
 * 业务网络客户端 —— 组合封装
 * 内部持有 BizHttp 实例，只暴露 INetClient 声明的方法
 * getClient() / 底层 sse() 等实现细节不对外暴露
 */
class NetClient implements INetClient {
  private bizHttp = new BizHttp();

  /** 初始化（供 initNetApi 调用，不在 INetClient 接口中） */
  init(config: BizHttpClientConfig): void {
    this.bizHttp.init(config);
  }

  // ===== 以下为 INetClient 接口方法，纯委托 =====

  get<T = any, F = any>(
    url: string,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  get<T = any, F = any>(
    url: string,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  get<T = any, F = any>(url: string, arg2?: any, arg3?: any) {
    return this.bizHttp.get<T, F>(url, arg2, arg3);
  }

  post<T = any, F = any>(
    url: string,
    data?: any,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  post<T = any, F = any>(
    url: string,
    data?: any,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  post<T = any, F = any>(url: string, data?: any, arg3?: any, arg4?: any) {
    return this.bizHttp.post<T, F>(url, data, arg3, arg4);
  }

  put<T = any, F = any>(
    url: string,
    data?: any,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  put<T = any, F = any>(
    url: string,
    data?: any,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  put<T = any, F = any>(url: string, data?: any, arg3?: any, arg4?: any) {
    return this.bizHttp.put<T, F>(url, data, arg3, arg4);
  }

  delete<T = any, F = any>(
    url: string,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  delete<T = any, F = any>(
    url: string,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  delete<T = any, F = any>(url: string, arg2?: any, arg3?: any) {
    return this.bizHttp.delete<T, F>(url, arg2, arg3);
  }

  patch<T = any, F = any>(
    url: string,
    data?: any,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  patch<T = any, F = any>(
    url: string,
    data?: any,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  patch<T = any, F = any>(url: string, data?: any, arg3?: any, arg4?: any) {
    return this.bizHttp.patch<T, F>(url, data, arg3, arg4);
  }

  sseStream<T = any>(
    url: string,
    body: unknown,
    callbacks?: SseStreamCallbacks<T>,
    opts?: SseStreamOptions<T>,
  ): Promise<SseFinalState> {
    return this.bizHttp.sseStream<T>(url, body, callbacks, opts);
  }
}

/** 全局单例 */
export const netClient = new NetClient();
