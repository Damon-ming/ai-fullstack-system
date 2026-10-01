// src/packages/biz-common/net/src/error-code.ts

/**
 * 错误码优先级：bizCode > httpCode > clientCode
 *
 * code 范围          │  来源           │  UI 语义
 * ───────────────────┼────────────────┼──────────────────
 * 1 - 10             │  客户端码       │  网络超时/取消/配置错误
 * 100 - 599          │  HTTP 状态码    │  标准 HTTP 错误（无结构化 body 时透传）
 * 10000+             │  服务端业务码   │  业务成功/失败
 *
 * 三个码段互不重叠，UI 只需根据范围即可判断错误来源，无需组合多个字段。
 */
export enum ClientErrorCode {
  /** 网络超时（含 axios timeout / fetch timeout） */
  NET_TIMEOUT = 1,
  /** 请求配置错误（如缺少 token、URL 非法） */
  CONFIG_ERR = 2,
  /** 请求被主动取消（用户操作 / AbortController） */
  CONFIG_CANCEL = 3,
}

/** 后端业务码区间（包含边界） */
export enum BizCodeRange {
  SUCCESS_MIN = 10000,
  /** HTTP 204 No Content 兜底成功码 */
  SUCCESS_NO_CONTENT = SUCCESS_MIN,
  SUCCESS_MAX = 39999,
  /** AI 业务成功码区间（与后端 BaseLLMSuccessResponse 对齐） */
  AI_SUCCESS_MIN = 100000,
  AI_SUCCESS_MAX = 299999,
  /** AI 业务失败码区间（与后端 BaseLLMFailedResponse 对齐） */
  AI_FAIL_MIN = 300000,
  AI_FAIL_MAX = 499999,
  /** 通用失败码区间（与后端 BaseFailedResponse 对齐） */
  FAIL_MIN = 40000,
  FAIL_MAX = 50000,
}

/** 判断是否为服务端业务码（成功 or 失败） */
export function isServerCode(code: number): boolean {
  return code >= BizCodeRange.SUCCESS_MIN;
}

/** 判断业务码分类 */
export function getBizCodeCategory(
  code: number,
): "success" | "fail" | "server" {
  // AI 业务码
  if (code >= BizCodeRange.AI_SUCCESS_MIN && code <= BizCodeRange.AI_SUCCESS_MAX)
    return "success";
  if (code >= BizCodeRange.AI_FAIL_MIN && code <= BizCodeRange.AI_FAIL_MAX)
    return "fail";
  // 通用业务码
  if (code >= BizCodeRange.SUCCESS_MIN && code <= BizCodeRange.SUCCESS_MAX)
    return "success";
  if (code >= BizCodeRange.FAIL_MIN && code <= BizCodeRange.FAIL_MAX)
    return "fail";
  // 其他 >= 10000 的码视为服务端返回（兼容未来扩展）
  if (code >= BizCodeRange.SUCCESS_MIN) return "server";
  return "fail";
}
