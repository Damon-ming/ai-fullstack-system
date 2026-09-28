import type {
  HttpClientConfig,
  InterceptorConfig,
  NormalizedRequest,
} from "../types";
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

function resolveRequestUrl(url: string, baseURL: string): string {
  // Keep relative URLs relative when baseURL is empty. This is required when
  // the browser and API are served from the same origin behind a reverse proxy.
  if (!baseURL || baseURL.trim() === "") return url;

  // Absolute URLs should not be resolved against baseURL.
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
    if (configuredHeaders && typeof configuredHeaders === "object") {
      Object.entries(configuredHeaders as Record<string, unknown>).forEach(
        ([key, value]) => {
          if (value != null) headers[key] = String(value);
        },
      );
    }
    headers.Accept = "text/event-stream";
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
        signal: opts?.signal ?? (commonConfig.signal as AbortSignal | undefined),
      },
      opts?.interceptors?.request,
    );

    const fetchHeaders = new Headers(normalizedRequest.headers);
    const requestData = normalizedRequest.data;
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
        fetchBody = JSON.stringify(requestData);
        if (!fetchHeaders.has("Content-Type"))
          fetchHeaders.set("Content-Type", "application/json");
      }
    }

    return fetch(normalizedRequest.url, {
      method: normalizedRequest.method,
      headers: fetchHeaders,
      body: fetchBody,
      signal: normalizedRequest.signal ?? opts?.signal,
      credentials: normalizedRequest.withCredentials
        ? "include"
        : "same-origin",
    });
  }
}
