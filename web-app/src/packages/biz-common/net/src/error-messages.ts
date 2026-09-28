// src/packages/biz-common/net/src/error-messages.ts

import { ClientErrorCode } from "./error-code";

/** 开发环境专用的英文错误映射表 */
export const ERROR_MESSAGES = {
  // 客户端错误码映射
  [ClientErrorCode.NET_TIMEOUT]:
    "Network request timeout, please check network connection.",
  [ClientErrorCode.CONFIG_ERR]: "Request configuration error.",
  [ClientErrorCode.CONFIG_CANCEL]: "Request was canceled.",
  [ClientErrorCode.HTTP_3XX_ERR]: "HTTP redirection error.",
  [ClientErrorCode.HTTP_4XX_ERR]: "HTTP client error.",
  [ClientErrorCode.HTTP_5XX_ERR]: "HTTP server error.",
  [ClientErrorCode.NET_ERROR]:
    "Network request failed, please check the network connection.",
  bizError: (bizCode: number) => `Business error, bizCode: ${bizCode}`,
  unknownBizCode: (bizCode: number) => `Unknown business code: ${bizCode}`,
  emptyResponse: "API response body is empty.",
  unknownError: "Unknown network or execution error.",
} as const;

/** HTTP Status 状态码解析辅助工具 */
export const HTTP_STATUS_MESSAGES: Record<number, string> = {
  301: "301 Moved Permanently",
  302: "302 Found / Moved Temporarily",
  400: "400 Bad Request",
  401: "401 Unauthorized",
  403: "403 Forbidden",
  404: "404 Not Found",
  405: "405 Method Not Allowed",
  408: "408 Request Timeout",
  429: "429 Too Many Requests",
  500: "500 Internal Server Error",
  502: "502 Bad Gateway",
  503: "503 Service Unavailable",
  504: "504 Gateway Timeout",
};

/** 获取 HTTP 状态码的 fallback 提示 */
export function getHttpStatusMessage(
  httpCode: number,
  defaultMsg?: string,
): string {
  if (HTTP_STATUS_MESSAGES[httpCode]) {
    return HTTP_STATUS_MESSAGES[httpCode];
  }
  if (httpCode >= 300 && httpCode < 400)
    return ERROR_MESSAGES[ClientErrorCode.HTTP_3XX_ERR];
  if (httpCode >= 400 && httpCode < 500)
    return ERROR_MESSAGES[ClientErrorCode.HTTP_4XX_ERR];
  if (httpCode >= 500 && httpCode < 600)
    return ERROR_MESSAGES[ClientErrorCode.HTTP_5XX_ERR];
  return defaultMsg || `HTTP Status Code: ${httpCode}`;
}
