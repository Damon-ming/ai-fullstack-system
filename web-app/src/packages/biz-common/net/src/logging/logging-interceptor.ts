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
import { createLogger, formatBody, formatTime } from "@ming/core-log";

const log = createLogger("net");

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

      log.info(`${method?.toUpperCase()} ${url}`, {
        params: formatBody(params),
        body: formatBody(data),
      });

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

      const level =
        status >= 200 && status < 300
          ? "info"
          : status >= 400
            ? "error"
            : "warn";

      log[level](
        `${config?.method?.toUpperCase()} ${config?.url} → ${status} (${formatTime(elapsed)})`,
        { body: formatBody(data) },
      );

      return response;
    },
    onRejected: (error: any) => {
      const config = error?.config ?? error?.response?.config ?? {};
      const startTime = (config as any).__netStartTime ?? Date.now();
      const elapsed = Date.now() - startTime;

      log.error(
        `${config?.method?.toUpperCase()} ${config?.url} → ${error?.status || "NETWORK_ERROR"} (${formatTime(elapsed)})`,
        error,
      );

      return Promise.reject(error);
    },
  };

  return { requestLog, responseLog };
}
