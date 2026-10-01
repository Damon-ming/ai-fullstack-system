import { ClientErrorCode } from "../error-code";
import { ERROR_MESSAGES, getHttpStatusMessage } from "../error-messages";
import type { BizApiErrorResponse } from "../types";

export function buildHttpCodeError<F = any>(
  httpCode: number,
  rawRes?: Record<string, any>,
): BizApiErrorResponse<F> {
  let code: ClientErrorCode = ClientErrorCode.HTTP_4XX_ERR;
  if (httpCode >= 300 && httpCode < 400) code = ClientErrorCode.HTTP_3XX_ERR;
  else if (httpCode >= 500 && httpCode < 600)
    code = ClientErrorCode.HTTP_5XX_ERR;

  return {
    code,
    clientData: {
      message: rawRes?.message || rawRes?.msg || getHttpStatusMessage(httpCode),
      httpCode,
      rawServerRes: rawRes,
    },
  };
}

// todo 补齐工业判断场景
export function formatAxiosException<F = any>(err: any): BizApiErrorResponse<F> {
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

  if (err.response) {
    return buildHttpCodeError<F>(err.response.status, err.response.data);
  }

  // ① axios 超时错误码
  // ② Node 超时错误码
  // ③ 错误信息里含 "timeout"
  if (
    err.code === "ECONNABORTED" ||
    err.code === "ETIMEDOUT" ||
    /timeout/i.test(err.message || "")
  ) {
    return {
      code: ClientErrorCode.NET_TIMEOUT,
      clientData: {
        message: ERROR_MESSAGES[ClientErrorCode.NET_TIMEOUT],
        rawServerRes: err.config || undefined,
      },
    };
  }

  return {
    code: ClientErrorCode.NET_ERROR,
    clientData: {
      message: err.message || ERROR_MESSAGES.unknownError,
      rawServerRes: err,
    },
  };
}

export function formatSseException(err: any): BizApiErrorResponse {
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
    code: ClientErrorCode.HTTP_UNKNOWN_CLIENT_ERR,
    clientData: {
      message: err?.message || ERROR_MESSAGES.unknownError,
      httpCode: err?.status,
      rawServerRes: err?.body ? { body: err.body } : undefined,
    },
  };
}
