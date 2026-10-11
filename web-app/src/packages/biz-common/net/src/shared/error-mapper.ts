// src/packages/biz-common/net/src/shared/error-mapper.ts
import { ClientErrorCode, isServerCode, ErrorCode } from "../error-code";
import {
  ERROR_MESSAGES,
  getHttpStatusMessage,
  getServerSafeMessage,
} from "../error-messages";
import type { BizApiErrorResponse } from "../shared/types";

/**
 * 从服务端原始错误响应中提取 error_msg。
 * 后端 BaseFailedResponse 格式: { code: number, data: { error_msg: string } }
 */
function _extractErrorMsg(rawRes?: Record<string, any>): string | undefined {
  if (!rawRes) return undefined;
  // 从 data.error_msg 提取（后端标准失败响应格式）
  if (rawRes.data && typeof rawRes.data === "object" && rawRes.data.error_msg) {
    return rawRes.data.error_msg;
  }
  return undefined;
}

/**
 * 非 2xx HTTP 响应的错误构造
 *
 * 优先级：bizCode > httpCode
 * - 服务端返回了结构化 body（含业务 code）→ 用业务 code
 * - 服务端返回了非结构化 body（HTML/反向代理拦截）→ 用 HTTP 状态码
 */
export function buildHttpCodeError<F = any>(
  httpCode: number,
  rawRes?: Record<string, any>,
): BizApiErrorResponse<F> {
  // 服务端返回了结构化的业务错误体 {code, data, message}
  if (rawRes && typeof rawRes.code === "number" && isServerCode(rawRes.code)) {
    const errorMsg = _extractErrorMsg(rawRes);
    return {
      code: rawRes.code,
      data: (rawRes.data ?? undefined) as F | undefined,
      clientData: {
        message:
          errorMsg ||
          getServerSafeMessage(rawRes.code) ||
          getHttpStatusMessage(httpCode),
      },
    };
  }

  // 服务端未返回结构化错误 → 直接透传 HTTP 状态码
  const errorMsg = _extractErrorMsg(rawRes);
  return {
    code: httpCode,
    clientData: {
      message: errorMsg || getHttpStatusMessage(httpCode),
    },
  };
}

/**
 * axios 异常格式化 —— 纯客户端场景（无 HTTP 响应）
 */
export function formatAxiosException<F = any>(
  err: any,
): BizApiErrorResponse<F> {
  // 请求被取消
  if (
    err.message?.includes("canceled") ||
    err.message?.includes("cancelled") ||
    err.code === "ERR_CANCELED"
  ) {
    return {
      code: ClientErrorCode.CONFIG_CANCEL,
      clientData: { message: ERROR_MESSAGES[ClientErrorCode.CONFIG_CANCEL] },
    };
  }

  // 服务端返回了 HTTP 错误响应（有 response 对象）
  if (err.response) {
    return buildHttpCodeError<F>(err.response.status, err.response.data);
  }

  // 网络超时
  if (
    err.code === "ECONNABORTED" ||
    err.code === "ETIMEDOUT" ||
    /timeout/i.test(err.message || "")
  ) {
    return {
      code: ClientErrorCode.NET_TIMEOUT,
      clientData: { message: ERROR_MESSAGES[ClientErrorCode.NET_TIMEOUT] },
    };
  }

  // 其他客户端错误（配置错误等）
  return {
    code: ClientErrorCode.CONFIG_ERR,
    clientData: {
      message: err.message || ERROR_MESSAGES.unknownError,
    },
  };
}

/**
 * SSE 异常格式化
 */
export function formatSseException(err: any): BizApiErrorResponse {
  // 请求被取消
  if (
    err.name === "AbortError" ||
    err.message?.includes("canceled") ||
    err.message?.includes("cancelled")
  ) {
    return {
      code: ClientErrorCode.CONFIG_CANCEL,
      clientData: { message: ERROR_MESSAGES[ClientErrorCode.CONFIG_CANCEL] },
    };
  }

  // 网络超时
  if (
    err.message?.includes("timeout") ||
    err.message?.includes("NetworkError") ||
    err.message?.includes("Failed to fetch")
  ) {
    return {
      code: ClientErrorCode.NET_TIMEOUT,
      clientData: { message: ERROR_MESSAGES[ClientErrorCode.NET_TIMEOUT] },
    };
  }

  return {
    code: ClientErrorCode.CONFIG_ERR,
    clientData: {
      message: err?.message || ERROR_MESSAGES.unknownError,
    },
  };
}

/**
 * SSE 错误事件 payload 构造
 *
 * 服务端通过 event: error 通知异常终止时，payload 格式为:
 * { code: number, data: { error_msg: string } }
 *
 * 转换为统一的 BizApiErrorResponse
 */
export function buildSseErrorPayload(payload: {
  code?: number;
  data?: unknown;
}): BizApiErrorResponse {
  const code = payload.code ?? ErrorCode.SYSTEM.UNKNOWN;
  const errorMsg: string =
    payload.data &&
    typeof payload.data === "object" &&
    (payload.data as { error_msg?: string }).error_msg
      ? (payload.data as { error_msg?: string }).error_msg!
      : getServerSafeMessage(code);
  return {
    code,
    data: payload.data,
    clientData: { message: errorMsg },
  };
}
