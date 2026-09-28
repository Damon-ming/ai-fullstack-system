// src/packages/biz-common/net/src/error-code.ts
/** 客户端本地错误码 */
export enum ClientErrorCode {
  /** 网络超时/无网络 */
  NET_TIMEOUT = 1,
  /** 请求配置错误/取消 */
  CONFIG_ERR = 2,
  CONFIG_CANCEL = 3,
  /** 3xx 重定向异常 */
  HTTP_3XX_ERR = 4,
  /** 4xx 客户端错误 */
  HTTP_4XX_ERR = 5,
  /** 5xx 服务端错误 */
  HTTP_5XX_ERR = 6,
  HTTP_UNKNOWN_ERR = 7,
  HTTP_BODY_NULL_ERR = 8,
  HTTP_UNKNOWN_CLIENT_ERR = 9,
  NET_ERROR = 10,
}

/** 后端业务 bizCode 区间（包含边界） */
export enum BizCodeRange {
  SUCCESS_MIN = 10000,
  SUCCESS_204 = SUCCESS_MIN,
  SUCCESS_MAX = 39999,
  FAIL_MIN = 40000,
  FAIL_MAX = 50000,
}

/** 获取业务错误码分类 */
export function getBizCodeCategory(
  bizCode: number,
): "success" | "fail" | "unknown" {
  if (
    bizCode >= BizCodeRange.SUCCESS_MIN &&
    bizCode <= BizCodeRange.SUCCESS_MAX
  ) {
    return "success";
  }
  if (bizCode >= BizCodeRange.FAIL_MIN && bizCode <= BizCodeRange.FAIL_MAX) {
    return "fail";
  }
  return "unknown";
}
