// src/packages/biz-common/net/src/shared/error-mapper.ts
import { ClientErrorCode, isServerCode } from "../error-code";
import { ERROR_MESSAGES, getHttpStatusMessage } from "../error-messages";
import type { BizApiErrorResponse } from "../shared/types";

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
    return {
      code: rawRes.code,
      data: (rawRes.data ?? undefined) as F | undefined,
      clientData: {
        message: rawRes.message || rawRes.msg || getHttpStatusMessage(httpCode),
      },
    };
  }

  // 服务端未返回结构化错误 → 直接透传 HTTP 状态码
  return {
    code: httpCode,
    clientData: {
      message: rawRes?.message || rawRes?.msg || getHttpStatusMessage(httpCode),
    },
  };
}

/**
 * axios 异常格式化 —— 纯客户端场景（无 HTTP 响应）
 */
export function formatAxiosException<F = any>(err: any): BizApiErrorResponse<F> {
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
