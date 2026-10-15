// src/packages/biz-common/net/src/error-messages.ts

import { ClientErrorCode, ServerSubSystem, getBusiness } from "./error-code";

// ---------------------------------------------------------------------------
// 客户端错误码映射 —— 开发环境专用
// ---------------------------------------------------------------------------

export const ERROR_MESSAGES: Record<number | string, string> = {
  [ClientErrorCode.NET_TIMEOUT]:
    "CLIENT:Network request timeout, please check network connection.",
  [ClientErrorCode.CONFIG_ERR]: "CLIENT:Request configuration error.",
  [ClientErrorCode.CONFIG_CANCEL]: "CLIENT:Request was canceled.",
  [ClientErrorCode.NET_UNREACHABLE]:
    "CLIENT:Unable to connect to server, please try again later.",
  unknownError: "CLIENT:Unknown network or execution error.",
};

// ---------------------------------------------------------------------------
// HTTP 状态码映射 —— 仅用于构造 data.error_msg，不参与逻辑分支
// ---------------------------------------------------------------------------

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

/** 获取 HTTP 状态码的描述 */
export function getHttpStatusMessage(
  httpCode: number,
  defaultMsg?: string,
): string {
  if (HTTP_STATUS_MESSAGES[httpCode]) {
    return HTTP_STATUS_MESSAGES[httpCode];
  }
  return defaultMsg || `CLIENT:HTTP ${httpCode}`;
}

// ---------------------------------------------------------------------------
// 服务端安全错误描述 —— 与后端 server_error.py get_safe_message() 对齐
// 不含内部细节（堆栈、SQL、密钥信息等），仅提示用户操作
// ---------------------------------------------------------------------------

const _SAFE_MESSAGES: Record<number, string> = {
  [ServerSubSystem.DATABASE]: "数据服务暂不可用，请稍后重试",
  [ServerSubSystem.ENCRYPTION]: "安全服务异常，请重新建立会话",
  [ServerSubSystem.UPLOAD]: "文件处理失败，请重试",
  [ServerSubSystem.AI]: "AI 服务暂不可用，请稍后重试",
  [ServerSubSystem.AUTH]: "认证失败，请重新登录",
  [ServerSubSystem.UNKNOWN]: "服务暂不可用，请稍后重试",
};

const _DEFAULT_SAFE_MESSAGE = "服务暂不可用，请稍后重试";

/**
 * 根据子系统分类码返回给客户端的安全错误描述。
 * 用于服务端未返回具体 error_msg 时的兜底文案。
 */
export function getServerSafeMessage(subsystemCode: number): string {
  return _SAFE_MESSAGES[subsystemCode] || _DEFAULT_SAFE_MESSAGE;
}

/**
 * 从服务端错误响应中提取用户可见的错误信息。
 * 优先使用服务端返回的 error_msg（已脱敏），否则用子系统分类兜底。
 *
 * @param errorCode  完整错误码 (如 200002001)
 * @param errorMsg   服务端返回的 data.error_msg
 */
export function getErrorMessage(
  errorCode: number,
  errorMsg?: string,
): string {
  if (errorMsg) return errorMsg;
  // 根据错误码系统位匹配子系统
  const systemCode = _getSubSystemByErrorCode(errorCode);
  return getServerSafeMessage(systemCode);
}

// ---------------------------------------------------------------------------
// 错误码 → 子系统分类映射（用于兜底文案）
// ---------------------------------------------------------------------------

function _getSubSystemByErrorCode(errorCode: number): number {
  // 新格式: BB=00(预留), CCC=业务模块, 用 CCC 做子系统分类
  const business = getBusiness(errorCode);
  switch (business) {
    case 2: // 002 加密
      return ServerSubSystem.ENCRYPTION;
    case 3: // 003 认证
      return ServerSubSystem.AUTH;
    case 5: // 005 AI/Chat
      return ServerSubSystem.AI;
    case 6: // 006 上传
      return ServerSubSystem.UPLOAD;
    case 7: // 007 数据库/基础设施
      return ServerSubSystem.DATABASE;
    default:
      return ServerSubSystem.UNKNOWN;
  }
}
