// src/packages/biz-common/net/src/biz-http.ts
import {
  HttpManager,
  HttpClient,
  HttpClientConfig,
  RequestConfig,
  InterceptorConfig,
  NormalizedRequest,
} from "@ming/core-network";
import {
  BizCodeRange,
  ClientErrorCode,
  getBizCodeCategory,
} from "./error-code";
import type {
  BizApiResponse,
  BizHttpClientConfig,
  BizRequestCallbacks,
  BizRequestConfig,
  BizResult,
  ErrDataResponse,
  SseFinalState,
  SseGlobalMessageInterceptor,
  SseResponseHeadersInterceptor,
  SseStreamCallbacks,
  SseStreamOptions,
} from "./types";
import { ERROR_MESSAGES, getHttpStatusMessage } from "./error-messages";

const DEFAULT_TIMEOUT = 10000;

export class BizHttp {
  private httpManager: HttpManager;
  private sseResponseHeadersInterceptors: SseResponseHeadersInterceptor[] = [];
  private sseMessageInterceptors: SseGlobalMessageInterceptor[] = [];

  constructor(manager?: HttpManager) {
    this.httpManager = manager || new HttpManager();
  }

  /**
   * 外部快速初始化：配置 baseURL/timeout，并设为默认客户端
   */
  public init(config: BizHttpClientConfig): HttpClient {
    const {
      timeout = DEFAULT_TIMEOUT,
      sseResponseHeadersInterceptors,
      sseMessageInterceptors,
      axiosConfig,
      ...restConfig
    } = config;

    // 组装并处理包含 timeout 的 Axios 配置
    const mergedConfig: HttpClientConfig = {
      ...restConfig,
      axiosConfig: {
        timeout,
        ...axiosConfig,
      },
    };

    const client = this.httpManager.createClient(mergedConfig);
    this.httpManager.setDefaultClient(client);

    // 初始化 SSE 全局拦截器
    this.sseResponseHeadersInterceptors = sseResponseHeadersInterceptors
      ? Array.isArray(sseResponseHeadersInterceptors)
        ? sseResponseHeadersInterceptors
        : [sseResponseHeadersInterceptors]
      : [];
    this.sseMessageInterceptors = sseMessageInterceptors
      ? Array.isArray(sseMessageInterceptors)
        ? sseMessageInterceptors
        : [sseMessageInterceptors]
      : [];

    return client;
  }

  /**
   * 获取底层 HttpClient 实例（在此添加全局 Request / Response 拦截器）
   */
  public getClient(): HttpClient {
    return this.httpManager.getDefaultClient();
  }

  /**
   * 规范化单次请求配置，处理单次 timeout 等逻辑
   */
  private normalizeConfig(
    cfg?: BizRequestConfig,
  ): Omit<RequestConfig, "url" | "method"> | undefined {
    if (!cfg) return undefined;
    // ...rest 是对象解构赋值中的剩余操作符（Rest Operator），用于将解构后剩下的所有属性收集到一个新对象中。
    const { timeout, axiosConfig, ...rest } = cfg;

    return {
      ...rest,
      axiosConfig: {
        ...(timeout !== undefined ? { timeout } : {}),
        ...axiosConfig,
      },
    };
  }

  /**
   * 核心包装函数：永远 resolve [err, res]，绝不 reject
   */
  private async requestWrap<T = any, F = any>(
    requestPromise: Promise<{ httpCode: number; data?: BizApiResponse<T> }>,
    callbacks?: BizRequestCallbacks<T, F>,
    config?: BizRequestConfig,
  ): Promise<BizResult<T, F>> {
    const { onSuccess, onFailed, onFinally } = callbacks || {};
    let errRes: ErrDataResponse<F> | null = null;
    let successRes: BizApiResponse<T> | null = null;

    try {
      const coreRes = await requestPromise;
      const { httpCode, data: bizBody } = coreRes;

      // ========== 1. 特殊处理 HTTP 204 No Content ==========
      if (httpCode === 204) {
        successRes = {
          bizCode: BizCodeRange.SUCCESS_204,
          data: undefined as unknown as T, // 204 本身没有 body，返回 undefined
        };
      }

      // ========== 1. HTTP 状态码非 200 ==========
      else if (httpCode !== 200) {
        errRes = this.buildHttpCodeError<F>(
          httpCode,
          bizBody as Record<string, any>,
        );
      }

      // ========== 2. HTTP 200 但无返回体 ==========
      else if (!bizBody) {
        errRes = {
          bizCode: ClientErrorCode.HTTP_BODY_NULL_ERR,
        };
      }

      // ========== 3. HTTP 200 解析业务 bizCode ==========
      else {
        const { bizCode, data } = bizBody;
        const category = getBizCodeCategory(bizCode);

        if (category === "success") {
          successRes = {
            bizCode,
            data: data as T,
          };
        } else if (category === "fail") {
          errRes = {
            bizCode,
            errData: data as F,
          };
        } else {
          errRes = {
            bizCode: ClientErrorCode.HTTP_UNKNOWN_ERR,
          };
        }
      }
    } catch (rawErr: any) {
      // ========== 4. 捕获底层异常（网络中断/超时/配置错误） ==========
      errRes = this.formatAxiosException<F>(rawErr);
    }

    // ========== 5. 处理 Callbacks ==========
    if (errRes) {
      try {
        onFailed?.(errRes);
      } catch (e) {
        console.error("[BizHttp] onFailed callback error:", e);
      }
    } else if (successRes) {
      try {
        onSuccess?.(successRes);
      } catch (e) {
        console.error("[BizHttp] onSuccess callback error:", e);
      }
    }

    try {
      onFinally?.();
    } catch (e) {
      console.error("[BizHttp] onFinally callback error:", e);
    }

    return [errRes, successRes];
  }

  /** 构建 HTTP 非 200 错误 */
  private buildHttpCodeError<F>(
    httpCode: number,
    rawRes?: Record<string, any>,
  ): ErrDataResponse<F> {
    let bizCode: ClientErrorCode = ClientErrorCode.HTTP_4XX_ERR;
    if (httpCode >= 300 && httpCode < 400)
      bizCode = ClientErrorCode.HTTP_3XX_ERR;
    else if (httpCode >= 500 && httpCode < 600)
      bizCode = ClientErrorCode.HTTP_5XX_ERR;

    const message =
      rawRes?.message || rawRes?.msg || getHttpStatusMessage(httpCode);

    return {
      bizCode,
      clientErrData: { message, httpCode, rawServerRes: rawRes },
    };
  }

  /** 格式化 Axios 抛出的异常 */
  private formatAxiosException<F>(err: any): ErrDataResponse<F> {
    if (
      err.message?.includes("canceled") ||
      err.message?.includes("cancelled") ||
      err.code === "ERR_CANCELED"
    ) {
      return {
        bizCode: ClientErrorCode.CONFIG_CANCEL,
        clientErrData: {
          message: ERROR_MESSAGES[ClientErrorCode.CONFIG_CANCEL],
        },
      };
    }

    if (
      err.code === "ECONNABORTED" ||
      err.message?.includes("timeout") ||
      err.message?.includes("Network Error") ||
      !err.response
    ) {
      return {
        bizCode: ClientErrorCode.NET_TIMEOUT,
        clientErrData: {
          message: ERROR_MESSAGES[ClientErrorCode.NET_TIMEOUT],
          rawServerRes: err.config || undefined,
        },
      };
    }

    if (err.response) {
      return this.buildHttpCodeError<F>(err.response.status, err.response.data);
    }

    return {
      bizCode: ClientErrorCode.HTTP_UNKNOWN_CLIENT_ERR,
      clientErrData: {
        message: err.message || ERROR_MESSAGES.unknownError,
        rawServerRes: err,
      },
    };
  }

  private isCallbacks<T, F>(obj: any): obj is BizRequestCallbacks<T, F> {
    return (
      obj &&
      (typeof obj.onSuccess === "function" ||
        typeof obj.onFailed === "function" ||
        typeof obj.onFinally === "function")
    );
  }

  private parseArgs<T, F>(arg2?: any, arg3?: any) {
    const cfg = this.isCallbacks(arg2)
      ? undefined
      : (arg2 as BizRequestConfig | undefined);
    const callbacks = this.isCallbacks(arg2)
      ? arg2
      : (arg3 as BizRequestCallbacks<T, F> | undefined);
    return { cfg, callbacks };
  }

  // ========== 请求 API 封装 ==========

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
    const { cfg, callbacks } = this.parseArgs<T, F>(arg2, arg3);
    const finalCfg = this.normalizeConfig(cfg);
    return this.requestWrap<T, F>(
      this.httpManager.get<BizApiResponse<T>>(url, finalCfg),
      callbacks,
      cfg,
    );
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
    const { cfg, callbacks } = this.parseArgs<T, F>(arg3, arg4);
    const finalCfg = this.normalizeConfig(cfg);
    return this.requestWrap<T, F>(
      this.httpManager.post<BizApiResponse<T>>(url, data, finalCfg),
      callbacks,
      cfg,
    );
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
    const { cfg, callbacks } = this.parseArgs<T, F>(arg3, arg4);
    const finalCfg = this.normalizeConfig(cfg);
    return this.requestWrap<T, F>(
      this.httpManager.put<BizApiResponse<T>>(url, data, finalCfg),
      callbacks,
      cfg,
    );
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
    const { cfg, callbacks } = this.parseArgs<T, F>(arg2, arg3);
    const finalCfg = this.normalizeConfig(cfg);
    return this.requestWrap<T, F>(
      this.httpManager.delete<BizApiResponse<T>>(url, finalCfg),
      callbacks,
      cfg,
    );
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
    const { cfg, callbacks } = this.parseArgs<T, F>(arg3, arg4);
    const finalCfg = this.normalizeConfig(cfg);
    return this.requestWrap<T, F>(
      this.httpManager.patch<BizApiResponse<T>>(url, data, finalCfg),
      callbacks,
      cfg,
    );
  }

  /**
   * 【通用SSE流式接口】业务层完整封装（对齐 restful 的 requestWrap）
   *
   * 职责：
   * 1. 调用底层 sse（支持全局+单次请求拦截器，加载顺序：全局→单次）
   * 2. SSE 协议解析（流读取、buffer 拼接、data:/event:/id: 提取）
   * 3. 消息解析（parse，默认 JSON.parse；传 false 给原始字符串）
   * 4. 业务消息校验（可选 validateMessage，对齐 bizCode 解析）
   * 5. 消息级拦截器链（可选 messageInterceptors）
   * 6. 统一错误格式 ErrDataResponse（HTTP非2xx / 网络异常 / 取消）
   * 7. callbacks：onMessage / onError / onComplete
   *
   * 注意：错误不再 throw，统一走 onError 回调（对齐 requestWrap 的永不 reject 哲学）
   */
  public async sseStream<T = any>(
    url: string,
    body: unknown,
    callbacks: SseStreamCallbacks<T> = {},
    opts: SseStreamOptions<T> = {},
  ): Promise<SseFinalState> {
    const { onMessage, onError, onComplete } = callbacks;
    const {
      parse,
      validateMessage,
      messageInterceptors,
      onResponseHeaders,
      ...sseOpts
    } = opts;

    // 消息级拦截器归一化为数组
    const msgInterceptors = messageInterceptors
      ? Array.isArray(messageInterceptors)
        ? messageInterceptors
        : [messageInterceptors]
      : [];

    // 安全调用回调（对齐 requestWrap 的 try-catch 保护）
    const safeOnMessage = (
      payload: T,
      meta?: { event?: string; id?: string },
    ) => {
      try {
        onMessage?.(payload, meta);
      } catch (e) {
        console.error("[BizHttp.sseStream] onMessage error:", e);
      }
    };
    const safeOnError = (err: ErrDataResponse) => {
      try {
        onError?.(err);
      } catch (e) {
        console.error("[BizHttp.sseStream] onError error:", e);
      }
    };
    const safeOnComplete = () => {
      try {
        onComplete?.();
      } catch (e) {
        console.error("[BizHttp.sseStream] onComplete error:", e);
      }
    };

    try {
      const res = await this.sse(url, body, sseOpts);

      // ===== 全局响应头拦截器（先于单次 onResponseHeaders 执行）=====
      for (const interceptor of this.sseResponseHeadersInterceptors) {
        try {
          await interceptor.onFulfilled?.(res);
        } catch (e) {
          try {
            interceptor.onRejected?.(e);
          } catch {}
          // 全局响应头拦截器异常不中断流，只告警
          console.warn(
            "[BizHttp.sseStream] global response headers interceptor error:",
            e,
          );
        }
      }

      if (onResponseHeaders) {
        try {
          await onResponseHeaders(res);
        } catch (e) {
          console.warn("[BizHttp.sseStream] onResponseHeaders error:", e);
        }
      }

      // ========== HTTP 非 2xx：统一错误格式 ==========
      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        const errRes = this.buildHttpCodeError(
          res.status,
          errText ? { message: errText, rawBody: errText } : undefined,
        );
        safeOnError(errRes);
        return { status: "error", error: errRes };
      }

      const reader = res.body?.getReader();
      if (!reader) {
        const errRes: ErrDataResponse = {
          bizCode: ClientErrorCode.HTTP_UNKNOWN_CLIENT_ERR,
          clientErrData: { message: "ReadableStream reader is not available" },
        };
        safeOnError(errRes);
        return { status: "error", error: errRes };
      }

      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let eventData = "";
      let eventType = "message";
      let lastEventId = "";

      // 处理一条完整 SSE 事件
      const dispatch = async () => {
        if (!eventData) return;
        const rawPayload = eventData.replace(/\n$/, "");
        const meta = { event: eventType, id: lastEventId };

        try {
          // ---- 1. 消息解析 ----
          let payload: T;
          if (parse === false) {
            payload = rawPayload as unknown as T;
          } else {
            const parser = parse ?? JSON.parse;
            payload = parser(rawPayload);
          }

          // ---- 2. 业务消息校验（可选，对齐 bizCode 解析）----
          if (validateMessage) {
            const { isError, error } = validateMessage(payload);
            if (isError && error) {
              safeOnError(error);
              return;
            }
          }

          // ---- 3. 消息级拦截器链（可选）----
          // 3.1 全局消息拦截器（先于单次执行）
          for (const interceptor of this.sseMessageInterceptors) {
            try {
              if (interceptor.onFulfilled) {
                payload = await interceptor.onFulfilled(payload, meta);
              }
            } catch (err) {
              if (interceptor.onRejected) {
                const handled = interceptor.onRejected(err);
                if (handled === false) return; // 吞掉这条消息
              }
              throw err;
            }
          }

          // 3.2 单次消息拦截器
          for (const interceptor of msgInterceptors) {
            try {
              if (interceptor.onFulfilled) {
                payload = await interceptor.onFulfilled(payload, meta);
              }
            } catch (err) {
              if (interceptor.onRejected) {
                const handled = interceptor.onRejected(err);
                if (handled === false) return; // 拦截器决定吞掉这条消息
              }
              throw err;
            }
          }

          // ---- 4. 抛给业务 ----
          safeOnMessage(payload, meta);
        } catch (e) {
          // 单条消息解析/拦截失败不中断流，只告警跳过
          console.warn("[BizHttp.sseStream] message process failed", {
            raw: rawPayload,
            error: e,
          });
        } finally {
          eventData = "";
          eventType = "message";
          lastEventId = "";
        }
      };

      const processLine = (line: string): void => {
        if (line.startsWith(":")) return; // 注释行
        if (line.startsWith("data:"))
          eventData += line.slice(5).trimStart() + "\n";
        else if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("id:")) lastEventId = line.slice(3).trim();
      };

      // ========== 流读取循环 ==========
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            if (line === "") {
              await dispatch();
              continue;
            }
            processLine(line);
          }
        }
        // 流结束时处理 buffer 中残留的未空行收尾事件
        if (buffer.trim()) {
          const remaining = buffer.split("\n");
          for (const line of remaining) {
            if (line === "") {
              await dispatch();
            } else {
              processLine(line);
            }
          }
          await dispatch();
        }
        safeOnComplete();
        return { status: "complete" };
      } finally {
        reader.releaseLock();
      }
    } catch (rawErr: any) {
      // ========== 网络异常 / 取消 / 配置错误：统一格式化 ==========
      const errRes = this.formatSseException(rawErr);
      safeOnError(errRes);
      return { status: "error", error: errRes };
    }
  }

  /**
   * 格式化 SSE 异常（对齐 formatAxiosException，区分取消/超时/未知）
   */
  private formatSseException(err: any): ErrDataResponse {
    if (
      err.name === "AbortError" ||
      err.message?.includes("canceled") ||
      err.message?.includes("cancelled")
    ) {
      return {
        bizCode: ClientErrorCode.CONFIG_CANCEL,
        clientErrData: {
          message: ERROR_MESSAGES[ClientErrorCode.CONFIG_CANCEL],
        },
      };
    }
    if (
      err.message?.includes("timeout") ||
      err.message?.includes("NetworkError") ||
      err.message?.includes("Failed to fetch")
    ) {
      return {
        bizCode: ClientErrorCode.NET_TIMEOUT,
        clientErrData: { message: ERROR_MESSAGES[ClientErrorCode.NET_TIMEOUT] },
      };
    }
    return {
      bizCode: ClientErrorCode.HTTP_UNKNOWN_CLIENT_ERR,
      clientErrData: {
        message: err?.message || ERROR_MESSAGES.unknownError,
        httpCode: err?.status,
        rawServerRes: err?.body ? { body: err.body } : undefined,
      },
    };
  }

  /**
   * SSE 底层请求透传（上层一般不直接调用，用 sseStream）
   */
  public async sse(
    url: string,
    body?: unknown,
    opts?: {
      signal?: AbortSignal;
      extraHeaders?: Record<string, string>;
      interceptors?: {
        request?:
          | InterceptorConfig<NormalizedRequest>
          | InterceptorConfig<NormalizedRequest>[];
      };
    },
  ): Promise<Response> {
    return this.httpManager.sse(url, body, opts);
  }
}

export const bizHttp = new BizHttp();
