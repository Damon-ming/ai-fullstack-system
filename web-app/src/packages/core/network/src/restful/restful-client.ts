// web-app/src/packages/core/network/src/restful/restful-client.ts
import axios, {
  AxiosHeaderValue,
  AxiosInstance,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from "axios";
import type { ApiResponse, HttpClientConfig, RequestConfig } from "./types";
import type { NormalizedRequest, NormalizedResponse } from "../shared/types";
import { InterceptorPipeline } from "../shared/interceptor-pipeline";

export class RestfulClient {
  private readonly instance: AxiosInstance;

  constructor(
    config: HttpClientConfig,
    private readonly pipeline: InterceptorPipeline,
  ) {
    this.instance = axios.create({
      baseURL: config.baseURL,
      // ??: 如果 config.headers 是 null 或 undefined，就用 {} 代替
      headers: config.headers ?? {},
      ...config.axiosConfig,
    });
  }

  private toNormalizedRequest(
    cfg: InternalAxiosRequestConfig,
  ): NormalizedRequest {
    const headers: Record<string, string> = {};
    if (cfg.headers) {
      // AxiosHeaders 类型上没有 forEach 方法，直接调用会报编译错误。作者用 as any "骗过"编译器，让它允许调用。
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
      responseType: cfg.responseType as NormalizedRequest["responseType"],
      signal: cfg.signal as AbortSignal | undefined,
    };
  }

  private fromNormalizedRequest(
    normalized: NormalizedRequest,
    target: InternalAxiosRequestConfig,
  ) {
    target.url = normalized.url;
    target.method = normalized.method.toLowerCase() as any;
    target.data = normalized.data;
    target.params = normalized.params;
    target.timeout = normalized.timeout;
    if (normalized.responseType)
      target.responseType = normalized.responseType as any;
    if (normalized.signal) target.signal = normalized.signal;
    // 把一个对象，变成一个"键值对数组"，
    Object.entries(normalized.headers).forEach(([key, value]) => {
      (target.headers as any).set?.(key, value);
    });
    return target;
  }

  private toNormalizedResponse<T>(
    response: AxiosResponse<T>,
  ): NormalizedResponse<T> {
    const headers: Record<string, string> = {};
    if (response.headers) {
      (response.headers as any).forEach?.((value: string, key: string) => {
        headers[key] = value;
      });
    }
    return {
      data: response.data,
      status: response.status,
      // 状态码对应的文字描述
      statusText: response.statusText,
      headers,
      config: this.toNormalizedRequest(
        response.config as InternalAxiosRequestConfig,
      ),
    };
  }

  async request<T = any>(config: RequestConfig): Promise<ApiResponse<T>> {
    let axiosConfig = {
      url: config.url,
      method: config.method,
      params: config.params,
      data: config.data,
      headers: config.headers,
      ...config.axiosConfig,
    } as InternalAxiosRequestConfig;
    axiosConfig.headers = axiosConfig.headers || {};

    const normalizedRequest = await this.pipeline.runRequest(
      this.toNormalizedRequest(axiosConfig),
      config.interceptors?.request,
    );
    axiosConfig = this.fromNormalizedRequest(normalizedRequest, axiosConfig);

    let rawResponse: AxiosResponse<T>;
    try {
      rawResponse = await this.instance.request<T>(axiosConfig);
    } catch (error) {
      throw await this.pipeline.runRejected(
        error,
        config.interceptors?.response,
      );
    }

    const normalizedResponse = await this.pipeline.runResponse(
      this.toNormalizedResponse(rawResponse),
      config.interceptors?.response,
    );

    return {
      code: normalizedResponse.status,
      data: normalizedResponse.data,
    };
  }

  get<T = any>(url: string, config?: Omit<RequestConfig, "url" | "method">) {
    return this.request<T>({ url, method: "GET", ...config });
  }

  post<T = any>(
    url: string,
    data?: any,
    config?: Omit<RequestConfig, "url" | "method" | "data">,
  ) {
    return this.request<T>({ url, method: "POST", data, ...config });
  }

  put<T = any>(
    url: string,
    data?: any,
    config?: Omit<RequestConfig, "url" | "method" | "data">,
  ) {
    return this.request<T>({ url, method: "PUT", data, ...config });
  }

  delete<T = any>(url: string, config?: Omit<RequestConfig, "url" | "method">) {
    return this.request<T>({ url, method: "DELETE", ...config });
  }

  patch<T = any>(
    url: string,
    data?: any,
    config?: Omit<RequestConfig, "url" | "method" | "data">,
  ) {
    return this.request<T>({ url, method: "PATCH", data, ...config });
  }
}
