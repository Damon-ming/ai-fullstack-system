// src/packages/biz-common/net/src/error-messages.ts

import { ClientErrorCode } from "./error-code";

/** 开发环境专用的英文错误映射表 */
export const ERROR_MESSAGES = {
  // 客户端错误码映射
  [ClientErrorCode.NET_TIMEOUT]:
    "CLIENT:Network request timeout, please check network connection.",
  [ClientErrorCode.CONFIG_ERR]: "CLIENT:Request configuration error.",
  [ClientErrorCode.CONFIG_CANCEL]: "CLIENT:Request was canceled.",
  unknownError: "CLIENT:Unknown network or execution error.",
} as const;

/** HTTP Status 状态码解析辅助工具 */
export const HTTP_STATUS_MESSAGES: Record<number, string> = {
  301: "CLIENT:301 Moved Permanently",
  302: "CLIENT:302 Found / Moved Temporarily",
  400: "CLIENT:400 Bad Request",
  401: "CLIENT:401 Unauthorized",
  403: "CLIENT:403 Forbidden",
  404: "CLIENT:404 Not Found",
  405: "CLIENT:405 Method Not Allowed",
  408: "CLIENT:408 Request Timeout",
  429: "CLIENT:429 Too Many Requests",
  500: "CLIENT:500 Internal Server Error",
  502: "CLIENT:502 Bad Gateway",
  503: "CLIENT:503 Service Unavailable",
  504: "CLIENT:504 Gateway Timeout",
};

/** 获取 HTTP 状态码的描述（仅用于构造 clientData.message，不参与逻辑分支） */
export function getHttpStatusMessage(
  httpCode: number,
  defaultMsg?: string,
): string {
  if (HTTP_STATUS_MESSAGES[httpCode]) {
    return HTTP_STATUS_MESSAGES[httpCode];
  }
  return defaultMsg || `CLIENT:HTTP ${httpCode}`;
}
