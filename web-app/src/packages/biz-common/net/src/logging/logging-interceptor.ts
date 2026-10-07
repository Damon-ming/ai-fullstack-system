// web-app/src/packages/biz-common/net/src/logging/logging-interceptor.ts
/**
 * 全局日志拦截器 —— 纯能力，是否注入由上层（main.ts）决定
 *
 * 打印每个请求的：
 *   - 方法 + URL
 *   - 请求参数（params / data）
 *   - 响应状态 + 响应体
 *   - 耗时
 *
 * 用法：
 *   // main.ts（debug 环境）
 *   const logging = createLoggingInterceptors();
 *   client.addRequestInterceptor(logging.requestLog);
 *   client.addResponseInterceptor(logging.responseLog);
 */

import type { InterceptorConfig } from "@ming/core-network";

// ---------------------------------------------------------------------------
// 格式化工具
// ---------------------------------------------------------------------------

function formatBody(body: unknown): string {
  if (body === undefined || body === null) return "-";
  if (body instanceof FormData) {
    const entries: string[] = [];
    body.forEach((value, key) => {
      if (value instanceof File) {
        entries.push(`${key}=<File:${value.name}(${value.size}B)>`);
      } else {
        entries.push(`${key}=${String(value).slice(0, 100)}`);
      }
    });
    return `[FormData] ${entries.join(", ")}`;
  }
  if (body instanceof Blob) {
    return `<Blob:${body.size}B>`;
  }
  if (typeof body === "object") {
    try {
      const json = JSON.stringify(body);
      return json.length > 500 ? json.slice(0, 500) + "..." : json;
    } catch {
      return String(body);
    }
  }
  return String(body).slice(0, 200);
}

function formatTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

// ---------------------------------------------------------------------------
// 拦截器工厂
// ---------------------------------------------------------------------------

export function createLoggingInterceptors(): {
  requestLog: InterceptorConfig;
  responseLog: InterceptorConfig;
} {
  const requestLog: InterceptorConfig = {
    onFulfilled: (request) => {
      const { method, url, params, data } = request;
      const timestamp = new Date().toLocaleTimeString();

      console.log(
        `%c[Net] ➡️  ${timestamp} ${method?.toUpperCase()} ${url}\n` +
          `    params: ${formatBody(params)}\n` +
          `    body:   ${formatBody(data)}`,
        "color: #2196F3; font-weight: bold;",
      );

      // 在请求对象上挂载起始时间，供响应拦截器计算耗时
      (request as any).__netStartTime = Date.now();

      return request;
    },
  };

  const responseLog: InterceptorConfig = {
    onFulfilled: (response) => {
      const { status, data, config } = response;
      const startTime = (config as any).__netStartTime ?? Date.now();
      const elapsed = Date.now() - startTime;
      const timestamp = new Date().toLocaleTimeString();

      const statusColor =
        status >= 200 && status < 300
          ? "color: #4CAF50;"
          : status >= 400
            ? "color: #F44336;"
            : "color: #FF9800;";

      console.log(
        `%c[Net] ⬅️  ${timestamp} ${config?.method?.toUpperCase()} ${config?.url} → ${status} (${formatTime(elapsed)})\n` +
          `    body: ${formatBody(data)}`,
        `${statusColor} font-weight: bold;`,
      );

      return response;
    },
    onRejected: (error: any) => {
      const config = error?.config ?? error?.response?.config ?? {};
      const startTime = (config as any).__netStartTime ?? Date.now();
      const elapsed = Date.now() - startTime;
      const timestamp = new Date().toLocaleTimeString();

      console.log(
        `%c[Net] ❌ ${timestamp} ${config?.method?.toUpperCase()} ${config?.url} → ${error?.status || "NETWORK_ERROR"} (${formatTime(elapsed)})\n` +
          `    error: ${error?.message || String(error)}`,
        "color: #F44336; font-weight: bold;",
      );

      return Promise.reject(error);
    },
  };

  return { requestLog, responseLog };
}
