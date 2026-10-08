// web-app/src/packages/biz-common/net/src/biz-http.ts
import {
  HttpManager,
  type HttpClient,
  type HttpClientConfig,
} from "@ming/core-network";
import type { BizHttpClientConfig } from "./shared/types";
import type {
  BizRequestCallbacks,
  BizRequestConfig,
  BizResult,
} from "./restful/types";
import type {
  SseFinalState,
  SseStreamCallbacks,
  SseStreamOptions,
} from "./sse/types";
import type { INetClient } from "./interface";
import { BizRestClient } from "./restful/biz-rest-client";
import { BizSseClient } from "./sse/biz-sse-client";
import { createTokenInterceptor } from "./auth/token-interceptor";
import { createEncryptionInterceptors } from "./encryption/encryption-interceptor";
import { createLoggingInterceptors } from "./logging/logging-interceptor";

export class BizHttp implements INetClient {
  private readonly httpManager: HttpManager;
  private readonly restful: BizRestClient;
  private readonly sseClient: BizSseClient;

  constructor(manager?: HttpManager) {
    this.httpManager = manager || new HttpManager();
    this.restful = new BizRestClient(this.httpManager);
    this.sseClient = new BizSseClient(this.httpManager);
  }

  init(config: BizHttpClientConfig): HttpClient {
    const {
      timeout = BizRestClient.getDefaultTimeout(),
      sseResponseHeadersInterceptors,
      sseMessageInterceptors,
      enableAuth = false,
      enableEncryption = false,
      enableLogging = false,
      signatureSecret = "",
      axiosConfig,
      ...restConfig
    } = config;
    const clientConfig: HttpClientConfig = {
      ...restConfig,
      axiosConfig: { timeout, ...axiosConfig },
    };
    const client = this.httpManager.createClient(clientConfig);
    this.httpManager.setDefaultClient(client);
    this.sseClient.configure({
      sseResponseHeadersInterceptors,
      sseMessageInterceptors,
    });

    // 环境头：所有请求携带 X-Client-Env，服务端可据此区分 debug/release 行为
    client.addRequestInterceptor({
      onFulfilled: (request) => ({
        ...request,
        headers: {
          ...request.headers,
          "X-Client-Env": import.meta.env.DEV ? "debug" : "release",
        },
      }),
    });

    // 加密 + 签名拦截器：OkHttp 风格，一个开关注册/不注册
    if (enableEncryption && signatureSecret) {
      const encryption = createEncryptionInterceptors(
        (url) => this.get(url),
        (url, data) => this.post(url, data),
        signatureSecret,
      );
      client.addRequestInterceptor(encryption.requestEncrypt);
      client.addResponseInterceptor(encryption.responseDecrypt);
    }

    // 日志拦截器：debug 环境打印请求/响应详情
    if (enableLogging) {
      const logging = createLoggingInterceptors();
      client.addRequestInterceptor(logging.requestLog);
      client.addResponseInterceptor(logging.responseLog);
    }

    // Token 拦截器：自动注入设备 token（从 store 或请求参数）
    if (enableAuth) {
      const tokenInterceptor = createTokenInterceptor();
      client.addRequestInterceptor(tokenInterceptor);
    }

    return client;
  }

  /** Kept for initialization and advanced infrastructure configuration only. */
  getClient(): HttpClient {
    return this.httpManager.getDefaultClient();
  }

  get<T = any, F = any>(
    url: string,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  get<T = any, F = any>(
    url: string,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  get<T = any, F = any>(
    url: string,
    arg2?: any,
    arg3?: any,
  ): Promise<BizResult<T, F>> {
    return this.restful.get<T, F>(url, arg2, arg3);
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
  post<T = any, F = any>(
    url: string,
    data?: any,
    arg3?: any,
    arg4?: any,
  ): Promise<BizResult<T, F>> {
    return this.restful.post<T, F>(url, data, arg3, arg4);
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
  put<T = any, F = any>(
    url: string,
    data?: any,
    arg3?: any,
    arg4?: any,
  ): Promise<BizResult<T, F>> {
    return this.restful.put<T, F>(url, data, arg3, arg4);
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
  delete<T = any, F = any>(
    url: string,
    arg2?: any,
    arg3?: any,
  ): Promise<BizResult<T, F>> {
    return this.restful.delete<T, F>(url, arg2, arg3);
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
  patch<T = any, F = any>(
    url: string,
    data?: any,
    arg3?: any,
    arg4?: any,
  ): Promise<BizResult<T, F>> {
    return this.restful.patch<T, F>(url, data, arg3, arg4);
  }

  sseStream<T = any>(
    url: string,
    body: unknown,
    callbacks?: SseStreamCallbacks<T>,
    opts?: SseStreamOptions<T>,
  ): Promise<SseFinalState> {
    return this.sseClient.stream<T>(url, body, callbacks, opts);
  }
}

export const bizHttp = new BizHttp();
