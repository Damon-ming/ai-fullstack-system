// src/packages/core/network/src/http-manager.ts
import { HttpClient } from "./http-client";
import {
  ApiResponse,
  HttpClientConfig,
  InterceptorConfig,
  NormalizedRequest,
} from "./types";

export class HttpManager {
  // 私有默认客户端，外部无法直接修改
  // | 在 TypeScript 中表示联合类型（Union Type），意思是"或者"。
  private defaultClient: HttpClient | null = null;

  /** 创建全新 HttpClient 实例 */
  createClient(config: HttpClientConfig): HttpClient {
    return new HttpClient(config);
  }

  /**
   * 基于已有客户端派生子客户端（继承配置+拦截器）
   */
  createChildFrom(
    parent: HttpClient,
    // Partial<T> 是 TypeScript 内置的工具类型，用于将类型 T 中的所有属性变为可选（Optional）
    config: Partial<HttpClientConfig>,
  ): HttpClient {
    return parent.createChild(config);
  }

  /** 设置全局默认客户端 */
  setDefaultClient(client: HttpClient): void {
    this.defaultClient = client;
  }

  /** 获取全局默认客户端 */
  getDefaultClient(): HttpClient {
    if (!this.defaultClient) {
      throw new Error(
        "Default HttpClient not initialized, please setDefaultClient first",
      );
    }
    return this.defaultClient;
  }

  // 快捷方法：直接调用默认客户端，统一返回 ApiResponse
  get<T>(
    url: string,
    // Parameters 是 TypeScript 内置的工具类型，用于提取函数类型的参数列表，返回一个元组类型。
    // HttpClient["get"] 表示获取 HttpClient 类型中名为 get 的成员的类型。
    // Parameters<HttpClient["get"]>[1] —— 获取第2个参数的类型
    // Promise<ApiResponse<T>> 表示这个异步操作最终会成功返回一个 ApiResponse<T> 类型的值
    // 使用时需要 await 或 .then()
    cfg?: Parameters<HttpClient["get"]>[1],
  ): Promise<ApiResponse<T>> {
    return this.getDefaultClient().get<T>(url, cfg);
  }

  post<T>(
    url: string,
    data?: any,
    cfg?: Parameters<HttpClient["post"]>[2],
  ): Promise<ApiResponse<T>> {
    return this.getDefaultClient().post<T>(url, data, cfg);
  }

  put<T>(
    url: string,
    data?: any,
    cfg?: Parameters<HttpClient["put"]>[2],
  ): Promise<ApiResponse<T>> {
    return this.getDefaultClient().put<T>(url, data, cfg);
  }

  delete<T>(
    url: string,
    cfg?: Parameters<HttpClient["delete"]>[1],
  ): Promise<ApiResponse<T>> {
    return this.getDefaultClient().delete<T>(url, cfg);
  }

  patch<T>(
    url: string,
    data?: any,
    cfg?: Parameters<HttpClient["patch"]>[2],
  ): Promise<ApiResponse<T>> {
    return this.getDefaultClient().patch<T>(url, data, cfg);
  }

  async sse(
    url: string,
    body?: any,
    opts?: {
      signal?: AbortSignal;
      extraHeaders?: Record<string, string>;
      interceptors?: {
        request?:
          | InterceptorConfig<NormalizedRequest>
          | InterceptorConfig<NormalizedRequest>[];
      };
    },
  ) {
    return this.getDefaultClient().sse(url, body, opts);
  }
}
