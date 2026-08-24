import axios, {
  AxiosHeaderValue,
  AxiosInstance,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from "axios";
import type {
  ApiResponse,
  HttpClientConfig,
  NormalizedRequest,
  NormalizedResponse,
  RequestConfig,
} from "../types";
import { InterceptorPipeline } from "../shared/interceptor-pipeline";

export class RestfulClient {
  private readonly instance: AxiosInstance;

  constructor(
    config: HttpClientConfig,
    private readonly pipeline: InterceptorPipeline,
  ) {
    this.instance = axios.create({
      baseURL: config.baseURL,
      headers: config.headers ?? {},
      ...config.axiosConfig,
    });
  }

  getAxiosInstance(): AxiosInstance {
    return this.instance;
  }

  private toNormalizedRequest(cfg: InternalAxiosRequestConfig): NormalizedRequest {
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

  private fromNormalizedRequest(normalized: NormalizedRequest, target: InternalAxiosRequestConfig) {
    target.url = normalized.url;
    target.method = normalized.method.toLowerCase() as any;
    target.data = normalized.data;
    target.params = normalized.params;
    target.timeout = normalized.timeout;
    target.withCredentials = normalized.withCredentials;
    if (normalized.responseType) target.responseType = normalized.responseType as any;
    if (normalized.signal) target.signal = normalized.signal;
    Object.entries(normalized.headers).forEach(([key, value]) => {
      (target.headers as any).set?.(key, value);
    });
    return target;
  }

  private toNormalizedResponse<T>(response: AxiosResponse<T>): NormalizedResponse<T> {
    const headers: Record<string, string> = {};
    if (response.headers) {
      (response.headers as any).forEach?.((value: string, key: string) => {
        headers[key] = value;
      });
    }
    return {
      data: response.data,
      status: response.status,
      statusText: response.statusText,
      headers,
      config: this.toNormalizedRequest(response.config as InternalAxiosRequestConfig),
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
      throw await this.pipeline.runRejected(error, config.interceptors?.response);
    }

    const normalizedResponse = await this.pipeline.runResponse(
      this.toNormalizedResponse(rawResponse),
      config.interceptors?.response,
    );
    return { httpCode: normalizedResponse.status, data: normalizedResponse.data };
  }

  get<T = any>(url: string, config?: Omit<RequestConfig, "url" | "method">) {
    return this.request<T>({ url, method: "GET", ...config });
  }

  post<T = any>(url: string, data?: any, config?: Omit<RequestConfig, "url" | "method" | "data">) {
    return this.request<T>({ url, method: "POST", data, ...config });
  }

  put<T = any>(url: string, data?: any, config?: Omit<RequestConfig, "url" | "method" | "data">) {
    return this.request<T>({ url, method: "PUT", data, ...config });
  }

  delete<T = any>(url: string, config?: Omit<RequestConfig, "url" | "method">) {
    return this.request<T>({ url, method: "DELETE", ...config });
  }

  patch<T = any>(url: string, data?: any, config?: Omit<RequestConfig, "url" | "method" | "data">) {
    return this.request<T>({ url, method: "PATCH", data, ...config });
  }
}
