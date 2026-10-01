import type { HttpClientConfig } from "../restful/types";
import type { InterceptorConfig, NormalizedRequest } from "../shared/types";
import { InterceptorPipeline } from "../shared/interceptor-pipeline";

export interface SseRequestOptions {
  signal?: AbortSignal;
  extraHeaders?: Record<string, string>;
  interceptors?: {
    request?:
      | InterceptorConfig<NormalizedRequest>
      | InterceptorConfig<NormalizedRequest>[];
  };
}

// 当 baseURL 为空时，保持相对 URL 不变
// 请求的 URL，可能是相对的（/api/user），也可能是绝对的（https://x.com/api）
function resolveRequestUrl(url: string, baseURL: string): string {
  // Keep relative URLs relative when baseURL is empty. This is required when
  // the browser and API are served from the same origin behind a reverse proxy.
  if (!baseURL || baseURL.trim() === "") return url;

  // Absolute URLs should not be resolved against baseURL.
  // 如果 url 本身已经是绝对 URL（带协议前缀，如 http:、https:、ftp:），就原样返回，不用 baseURL 拼接
  // test 是 RegExp（正则对象）的方法
  if (/^[a-z][a-z\d+.-]*:/i.test(url)) return url;

  return new URL(url, baseURL).href;
}

/** Transport-only SSE implementation. It does not parse business messages. */
export class SseTransport {
  constructor(
    private readonly config: HttpClientConfig,
    private readonly pipeline: InterceptorPipeline,
  ) {}

  async request(
    url: string,
    body?: any,
    opts?: SseRequestOptions,
  ): Promise<Response> {
    const finalUrl = resolveRequestUrl(url, this.config.baseURL);
    const commonConfig = this.config.axiosConfig ?? {};
    const headers: Record<string, string> = {};
    Object.entries(this.config.headers ?? {}).forEach(([key, value]) => {
      if (value != null) headers[key] = String(value);
    });
    const configuredHeaders = commonConfig.headers;
    // typeof 是 JavaScript 的运算符，返回一个字符串，表示某个值的类型。
    // typeof {}         // → "object"
    // typeof []         // → "object"   ⚠️ 注意
    // typeof null       // → "object"   ⚠️ 注意
    if (configuredHeaders && typeof configuredHeaders === "object") {
      Object.entries(configuredHeaders as Record<string, unknown>).forEach(
        ([key, value]) => {
          if (value != null) headers[key] = String(value);
        },
      );
    }
    headers.Accept = "text/event-stream";
    // 是 JavaScript 内置方法，作用是把一个或多个对象的属性，"复制合并"到目标对象上。
    Object.assign(headers, opts?.extraHeaders ?? {});

    const normalizedRequest = await this.pipeline.runRequest(
      {
        url: finalUrl,
        method: "POST",
        headers,
        data: body,
        withCredentials:
          typeof commonConfig.withCredentials === "boolean"
            ? commonConfig.withCredentials
            : undefined,
        signal:
          opts?.signal ?? (commonConfig.signal as AbortSignal | undefined),
      },
      opts?.interceptors?.request,
    );

    const fetchHeaders = new Headers(normalizedRequest.headers);
    const requestData = normalizedRequest.data;
    // BodyInit: 表示"能作为 fetch 请求体的数据类型
    let fetchBody: BodyInit | undefined;
    if (requestData !== undefined && requestData !== null) {
      if (
        requestData instanceof FormData ||
        requestData instanceof Blob ||
        requestData instanceof URLSearchParams ||
        typeof requestData === "string"
      ) {
        fetchBody = requestData;
      } else {
        // 作用是把一个值（对象、数组等）转成 JSON 格式的字符串
        fetchBody = JSON.stringify(requestData);
        if (!fetchHeaders.has("Content-Type"))
          fetchHeaders.set("Content-Type", "application/json");
      }
    }
    // SSE 适合 fetch，是因为 fetch 原生支持"读取流式响应"（response.body 是可读流），能一段段读服务端推来的数据
    // SSE 的自动重连、格式解析等，用 fetch 时要自己实现。
    return fetch(normalizedRequest.url, {
      method: normalizedRequest.method,
      headers: fetchHeaders,
      body: fetchBody,
      signal: normalizedRequest.signal ?? opts?.signal,
      // "omit"	从不发送 Cookie
      // "same-origin"（默认）	同源请求才发 Cookie，跨域不发
      // "include"	同源和跨域都发 Cookie
      // todo
      credentials: normalizedRequest.withCredentials
        ? "include"
        : "same-origin",
    });
  }
}
