import type {
  ApiResponse,
  HttpClientConfig,
  InterceptorConfig,
  InterceptorConfigCollection,
  NormalizedRequest,
  RequestConfig,
} from "./types";
import { InterceptorPipeline } from "./shared/interceptor-pipeline";
import { RestfulClient } from "./restful/restful-client";
import { SseTransport } from "./sse/sse-transport";
import type { SseRequestOptions } from "./sse/sse-transport";
import type { AxiosInstance } from "axios";

/** Public facade combining REST and SSE transports without mixing their implementations. */
export class HttpClient {
  private readonly pipeline: InterceptorPipeline;
  private readonly restful: RestfulClient;
  private readonly sseTransport: SseTransport;

  constructor(private readonly config: HttpClientConfig) {
    if (typeof config.baseURL !== "string") throw new Error("HttpClientConfig.baseURL must be string");
    this.pipeline = new InterceptorPipeline(config.interceptors);
    this.restful = new RestfulClient(config, this.pipeline);
    this.sseTransport = new SseTransport(config, this.pipeline);
  }

  addRequestInterceptor(
    interceptor: InterceptorConfigCollection<NormalizedRequest>,
  ) {
    return this.pipeline.addRequestInterceptor(interceptor);
  }

  addResponseInterceptor(
    interceptor: InterceptorConfigCollection<any>,
  ) {
    return this.pipeline.addResponseInterceptor(interceptor as any);
  }

  getAxiosInstance(): AxiosInstance {
    return this.restful.getAxiosInstance();
  }

  request<T = any>(config: RequestConfig): Promise<ApiResponse<T>> {
    return this.restful.request<T>(config);
  }

  get<T = any>(url: string, config?: Omit<RequestConfig, "url" | "method">) {
    return this.restful.get<T>(url, config);
  }

  post<T = any>(url: string, data?: any, config?: Omit<RequestConfig, "url" | "method" | "data">) {
    return this.restful.post<T>(url, data, config);
  }

  put<T = any>(url: string, data?: any, config?: Omit<RequestConfig, "url" | "method" | "data">) {
    return this.restful.put<T>(url, data, config);
  }

  delete<T = any>(url: string, config?: Omit<RequestConfig, "url" | "method">) {
    return this.restful.delete<T>(url, config);
  }

  patch<T = any>(url: string, data?: any, config?: Omit<RequestConfig, "url" | "method" | "data">) {
    return this.restful.patch<T>(url, data, config);
  }

  sse(url: string, body?: any, opts?: SseRequestOptions): Promise<Response> {
    return this.sseTransport.request(url, body, opts);
  }

  createChild(config: Partial<HttpClientConfig>): HttpClient {
    const currentInterceptors = this.pipeline.getConfig();
    const asArray = <T,>(value?: T | T[]): T[] =>
      value ? (Array.isArray(value) ? value : [value]) : [];
    return new HttpClient({
      ...this.config,
      ...config,
      headers: { ...this.config.headers, ...config.headers },
      axiosConfig: { ...this.config.axiosConfig, ...config.axiosConfig },
      interceptors: {
        request: [
          ...asArray(currentInterceptors?.request),
          ...asArray(config.interceptors?.request),
        ],
        response: [
          ...asArray(currentInterceptors?.response),
          ...asArray(config.interceptors?.response),
        ],
      },
    });
  }
}

export type { SseRequestOptions } from "./sse/sse-transport";
