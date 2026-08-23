// src/packages/core/network/src/http-client.ts
import axios, {
  InternalAxiosRequestConfig,
  AxiosHeaderValue,
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
} from "axios";
import {
  RequestConfig,
  HttpClientConfig,
  ApiResponse,
  InterceptorConfig,
  CommonAxiosConfig,
  NormalizedResponse,
  NormalizedRequest,
} from "./types";

export class HttpClient {
  private instance: AxiosInstance;

  // 存储拦截器 ID，用于清理
  private globalRequestInterceptors: InterceptorConfig<NormalizedRequest>[] =
    [];
  private globalResponseInterceptors: InterceptorConfig<NormalizedResponse>[] =
    [];

  constructor(config: HttpClientConfig) {
    if (typeof config.baseURL !== "string")
      throw new Error("HttpClientConfig.baseURL must be string");

    this.instance = axios.create({
      baseURL: config.baseURL,
      headers: config.headers ?? {},
      ...config.axiosConfig,
    });

    this.setupInterceptors(config.interceptors);
  }

  private toNormalizedRequest(
    cfg: InternalAxiosRequestConfig,
  ): NormalizedRequest {
    const headers: Record<string, string> = {};
    if (cfg.headers) {
      (cfg.headers as any).forEach?.((value: AxiosHeaderValue, key: string) => {
        if (value != null) headers[key] = String(value);
      });
    }
    return {
      url: cfg.url ?? "",
      method: (cfg.method ?? "GET").toUpperCase(),
      headers,
      params: cfg.params,
      data: cfg.data,
      timeout: cfg.timeout,
      withCredentials: cfg.withCredentials,
      responseType: cfg.responseType as NormalizedRequest["responseType"],
      signal: cfg.signal as AbortSignal | undefined,
    };
  }

  private fromNormalizedRequest(
    normalized: NormalizedRequest,
    target: InternalAxiosRequestConfig,
  ): InternalAxiosRequestConfig {
    target.url = normalized.url;
    target.method = normalized.method.toLowerCase() as any;
    target.data = normalized.data;
    target.params = normalized.params;
    target.timeout = normalized.timeout;
    target.withCredentials = normalized.withCredentials;
    if (normalized.responseType)
      target.responseType = normalized.responseType as any;
    if (normalized.signal) target.signal = normalized.signal;
    const axiosHeaders = target.headers;
    Object.entries(normalized.headers).forEach(([k, v]) => {
      (axiosHeaders as any).set?.(k, v);
    });
    return target;
  }

  private toNormalizedResponse<T>(
    res: AxiosResponse<T>,
  ): NormalizedResponse<T> {
    const headers: Record<string, string> = {};
    if (res.headers) {
      (res.headers as any).forEach?.((value: string, key: string) => {
        headers[key] = value;
      });
    }
    return {
      data: res.data,
      status: res.status,
      statusText: res.statusText,
      headers,
      config: this.toNormalizedRequest(
        res.config as InternalAxiosRequestConfig,
      ),
    };
  }

  private fromNormalizedResponse<T>(
    normalized: NormalizedResponse<T>,
    target: AxiosResponse<T>,
  ): AxiosResponse<T> {
    target.data = normalized.data;
    target.status = normalized.status;
    target.statusText = normalized.statusText;
    const axiosHeaders = target.headers;
    Object.entries(normalized.headers).forEach(([k, v]) => {
      (axiosHeaders as any).set?.(k, v);
    });
    return target;
  }

  private setupInterceptors(interceptors: HttpClientConfig["interceptors"]) {
    if (!interceptors) return;

    if (interceptors.request) {
      const reqs = Array.isArray(interceptors.request)
        ? interceptors.request
        : [interceptors.request];
      this.globalRequestInterceptors.push(...reqs);
    }

    if (interceptors.response) {
      const resps = Array.isArray(interceptors.response)
        ? interceptors.response
        : [interceptors.response];
      this.globalResponseInterceptors.push(...resps);
    }
  }

  /** 动态添加全局请求拦截器 */
  addRequestInterceptor(
    interceptor:
      | InterceptorConfig<NormalizedRequest>
      | InterceptorConfig<NormalizedRequest>[],
  ): () => void {
    const list = Array.isArray(interceptor) ? interceptor : [interceptor];
    this.globalRequestInterceptors.push(...list);

    return () => {
      this.globalRequestInterceptors = this.globalRequestInterceptors.filter(
        (i) => !list.includes(i),
      );
    };
  }

  /** 动态添加全局响应拦截器 */
  addResponseInterceptor(
    interceptor:
      | InterceptorConfig<NormalizedResponse>
      | InterceptorConfig<NormalizedResponse>[],
  ): () => void {
    const list = Array.isArray(interceptor) ? interceptor : [interceptor];
    this.globalResponseInterceptors.push(...list);

    return () => {
      this.globalResponseInterceptors = this.globalResponseInterceptors.filter(
        (i) => !list.includes(i),
      );
    };
  }

  /**
   * 获取 axios 实例（用于高级操作）
   */
  getAxiosInstance(): AxiosInstance {
    return this.instance;
  }

  async request<T = any>(config: RequestConfig): Promise<ApiResponse<T>> {
    let axiosCfg: AxiosRequestConfig = {
      url: config.url,
      method: config.method,
      params: config.params,
      data: config.data,
      headers: config.headers,
      ...config.axiosConfig,
    };

    // 补全必要的默认字段以符合 InternalAxiosRequestConfig 类型
    let finalAxiosCfg = axiosCfg as InternalAxiosRequestConfig;
    finalAxiosCfg.headers = finalAxiosCfg.headers || {};

    // 这是 JavaScript 的对象解构赋值，用于从 config 对象中提取 interceptors 属性，并重命名为 singleInterceptors
    const { interceptors: singleInterceptors } = config;

    let normalizedReq = this.toNormalizedRequest(finalAxiosCfg);

    // ==================== 1. 请求拦截阶段 (Request) ====================
    // 1.1 执行 [全局] 请求拦截器
    // of 是 for...of 循环的关键词，用于遍历可迭代对象（如数组）中的每个元素。
    for (const interceptor of this.globalRequestInterceptors) {
      try {
        if (interceptor.onFulfilled) {
          normalizedReq = await interceptor.onFulfilled(normalizedReq);
        }
      } catch (err) {
        if (interceptor.onRejected) {
          await interceptor.onRejected(err);
        }
        throw err;
      }
    }

    // 1.2 执行 [单次] 请求拦截器（此时拿到的是已被全局拦截器修改过的 config）

    const singleReqs = singleInterceptors?.request
      ? Array.isArray(singleInterceptors.request)
        ? singleInterceptors.request
        : [singleInterceptors.request]
      : [];

    for (const interceptor of singleReqs) {
      try {
        if (interceptor.onFulfilled) {
          normalizedReq = await interceptor.onFulfilled(normalizedReq);
        }
      } catch (err) {
        if (interceptor.onRejected) {
          await interceptor.onRejected(err);
        }
        throw err;
      }
    }

    finalAxiosCfg = this.fromNormalizedRequest(normalizedReq, finalAxiosCfg);

    // ==================== 2. 发起网络请求 ====================
    let rawRes: AxiosResponse<T>;
    try {
      // 注意：使用 axios.request 基础方法，避免触发 axios 实例上的重复拦截器
      rawRes = await this.instance.request<T>(finalAxiosCfg);
    } catch (networkErr) {
      // 网络请求失败时的异常处理流
      let handledErr = networkErr;

      // 尝试让全局响应 onRejected 处理
      for (const interceptor of this.globalResponseInterceptors) {
        if (interceptor.onRejected) {
          try {
            handledErr = await interceptor.onRejected(handledErr);
          } catch (e) {
            handledErr = e;
          }
        }
      }

      // 尝试让单次响应 onRejected 处理（支持单个或数组，与全局行为对齐）
      const singleResps = singleInterceptors?.response
        ? Array.isArray(singleInterceptors.response)
          ? singleInterceptors.response
          : [singleInterceptors.response]
        : [];
      for (const interceptor of singleResps) {
        if (interceptor.onRejected) {
          try {
            handledErr = await interceptor.onRejected(handledErr);
          } catch (e) {
            handledErr = e;
          }
        }
      }
      throw handledErr;
    }

    let normalizedRes = this.toNormalizedResponse(rawRes);

    // ==================== 3. 响应拦截阶段 (Response) ====================
    // 3.1 执行 [全局] 响应拦截器
    for (const interceptor of this.globalResponseInterceptors) {
      try {
        if (interceptor.onFulfilled) {
          normalizedRes = await interceptor.onFulfilled(normalizedRes);
        }
      } catch (err) {
        if (interceptor.onRejected) {
          await interceptor.onRejected(err);
        }
        throw err;
      }
    }

    // 3.2 执行 [单次] 响应拦截器（此时拿到的是已经被全局响应拦截器处理过的 response）
    const singleResps = singleInterceptors?.response
      ? Array.isArray(singleInterceptors.response)
        ? singleInterceptors.response
        : [singleInterceptors.response]
      : [];

    for (const interceptor of singleResps) {
      try {
        if (interceptor.onFulfilled) {
          normalizedRes = await interceptor.onFulfilled(normalizedRes);
        }
      } catch (err) {
        if (interceptor.onRejected) {
          await interceptor.onRejected(err);
        }
        throw err;
      }
    }

    // 返回经过全局+单次响应拦截器处理后的结果，而非原始 rawRes
    return {
      httpCode: normalizedRes.status,
      data: normalizedRes.data,
    };
  }

  /** GET 请求，统一返回 ApiResponse */
  async get<T = any>(
    url: string,
    config?: Omit<RequestConfig, "url" | "method">,
  ): Promise<ApiResponse<T>> {
    return this.request<T>({ url, method: "GET", ...config });
  }

  /** POST 请求，统一返回 ApiResponse */
  async post<T = any>(
    url: string,
    data?: any,
    config?: Omit<RequestConfig, "url" | "method" | "data">,
  ): Promise<ApiResponse<T>> {
    return this.request<T>({ url, method: "POST", data, ...config });
  }

  /** PUT 请求，统一返回 ApiResponse */
  async put<T = any>(
    url: string,
    data?: any,
    config?: Omit<RequestConfig, "url" | "method" | "data">,
  ): Promise<ApiResponse<T>> {
    return this.request<T>({ url, method: "PUT", data, ...config });
  }

  /** DELETE 请求，统一返回 ApiResponse */
  async delete<T = any>(
    url: string,
    config?: Omit<RequestConfig, "url" | "method">,
  ): Promise<ApiResponse<T>> {
    return this.request<T>({ url, method: "DELETE", ...config });
  }

  /** PATCH 请求，统一返回 ApiResponse */
  async patch<T = any>(
    url: string,
    data?: any,
    config?: Omit<RequestConfig, "url" | "method" | "data">,
  ): Promise<ApiResponse<T>> {
    return this.request<T>({ url, method: "PATCH", data, ...config });
  }

  /**
   * SSE流式请求，底层fetch
   * 复用实例 baseURL、headers，执行【全局 + 单次】请求拦截器（加载顺序：全局→单次）
   * 不执行响应拦截器（SSE是分片流，无完整响应对象）
   */
  async sse(
    url: string,
    body?: any,
    opts?: {
      method?: "GET" | "POST";
      signal?: AbortSignal;
      extraHeaders?: Record<string, string>;
      interceptors?: {
        request?:
          | InterceptorConfig<NormalizedRequest>
          | InterceptorConfig<NormalizedRequest>[];
      };
    },
  ) {
    let finalUrl = new URL(url, this.instance.defaults.baseURL).href;
    const headers: Record<string, string> = {};
    const axiosDefaultHeaders = this.instance.defaults.headers;
    Object.entries(axiosDefaultHeaders.common ?? {}).forEach(([k, v]) => {
      if (v != null) headers[k] = String(v);
    });
    headers["Accept"] = "text/event-stream";
    Object.entries(opts?.extraHeaders ?? {}).forEach(([k, v]) => {
      headers[k] = v;
    });

    let normalizedReq: NormalizedRequest = {
      url: finalUrl,
      method: opts?.method ?? "POST",
      headers,
      data: body,
    };

    // ==================== 1. 请求拦截阶段 ====================
    // 1.1 执行【全局】请求拦截器
    for (const interceptor of this.globalRequestInterceptors) {
      try {
        if (interceptor.onFulfilled) {
          normalizedReq = await interceptor.onFulfilled(normalizedReq);
        }
      } catch (err) {
        if (interceptor.onRejected) await interceptor.onRejected(err);
        throw err;
      }
    }

    // 1.2 新增：执行【单次】请求拦截器（加载顺序：全局 → 单次，与 request() 一致）
    const singleReqs = opts?.interceptors?.request
      ? Array.isArray(opts.interceptors.request)
        ? opts.interceptors.request
        : [opts.interceptors.request]
      : [];

    for (const interceptor of singleReqs) {
      try {
        if (interceptor.onFulfilled) {
          normalizedReq = await interceptor.onFulfilled(normalizedReq);
        }
      } catch (err) {
        if (interceptor.onRejected) await interceptor.onRejected(err);
        throw err;
      }
    }

    // ==================== 2. 发起 fetch ====================
    const fetchHeaders = new Headers();
    Object.entries(normalizedReq.headers ?? {}).forEach(([k, v]) => {
      if (v != null) fetchHeaders.set(k, String(v));
    });

    const reqData = normalizedReq.data;
    let fetchBody: BodyInit | undefined;
    if (reqData !== undefined && reqData !== null) {
      if (
        reqData instanceof FormData ||
        reqData instanceof Blob ||
        reqData instanceof URLSearchParams ||
        typeof reqData === "string"
      ) {
        fetchBody = reqData;
      } else {
        fetchBody = JSON.stringify(reqData);
        if (!fetchHeaders.has("Content-Type")) {
          fetchHeaders.set("Content-Type", "application/json");
        }
      }
    }

    const fetchRes = await fetch(normalizedReq.url, {
      method: normalizedReq.method,
      headers: fetchHeaders,
      body: fetchBody,
      signal: opts?.signal,
      credentials: normalizedReq.withCredentials ? "include" : "same-origin",
    });
    return fetchRes;
  }

  createChild(config: Partial<HttpClientConfig>): HttpClient {
    // instance.defaults 实例的默认配置
    const currentConfig = this.instance.defaults;

    // 清洗父 common headers，剔除值为 undefined 的属性
    // 表示一个键为字符串、值为 AxiosHeaderValue 类型的对象。	AxiosHeaderValue值（value）的类型是 Axios 定义的 header 值类型
    const parentCommonHeaders: Record<string, AxiosHeaderValue> = {};
    const commonHeaders = currentConfig.headers.common ?? {};
    // currentConfig.headers.common 是指当前请求配置对象中，专门用于存放所有请求方法通用的 HTTP 头部信息的对象。
    for (const [key, value] of Object.entries(commonHeaders)) {
      //undefined:变量未赋值
      if (value !== undefined) {
        parentCommonHeaders[key] = value;
      }
    }

    const mergedInterceptors = this.mergeInterceptors(config.interceptors);

    const childConfig: HttpClientConfig = {
      baseURL: config.baseURL ?? currentConfig.baseURL ?? "",
      headers: {
        ...parentCommonHeaders,
        ...config.headers,
      },
      axiosConfig: {
        ...this.omit(currentConfig, ["baseURL", "timeout", "headers"]),
        ...config.axiosConfig,
      },

      interceptors: mergedInterceptors,
    };

    return new HttpClient(childConfig);
  }

  /** 合并父子拦截器：父级在前（先执行），子级在后追加 */
  private mergeInterceptors(
    child?: HttpClientConfig["interceptors"],
  ): HttpClientConfig["interceptors"] | undefined {
    const parentReq = this.globalRequestInterceptors;
    const parentRes = this.globalResponseInterceptors;
    const childReq = child?.request
      ? Array.isArray(child.request)
        ? child.request
        : [child.request]
      : [];
    const childRes = child?.response
      ? Array.isArray(child.response)
        ? child.response
        : [child.response]
      : [];

    const request = [...parentReq, ...childReq];
    const response = [...parentRes, ...childRes];

    if (request.length === 0 && response.length === 0) return undefined;
    return {
      request: request.length ? request : undefined,
      response: response.length ? response : undefined,
    };
  }

  // keyof 是 TypeScript 中的索引类型查询操作符（Index Type Query Operator），用于获取一个类型的所有属性键组成的联合类型。
  // keyof Person 就是把 Person 的属性名提取出来，变成一个"字符串联合类型"。
  private omit<T extends object, K extends keyof T>(
    obj: T,
    keys: K[],
  ): Omit<T, K> {
    const copy = { ...obj };
    keys.forEach((k) => delete copy[k]);
    return copy;
  }
}
