// src/packages/biz-common/net/src/header/common-header-interceptor.ts
/**
 * 公共请求头拦截器 —— 每次请求必须携带的 header。
 *
 * 当前注入：
 *   - X-System-Version : 系统版本号
 *   - X-Client-Env     : 运行环境（debug / release）
 *
 * 注：加密协议相关 header（X-Encrypt-Version / X-Signature-Version）
 * 由 encryption-interceptor 管理，仅在加密启用时注入。
 */

import type { NormalizedRequest } from "@ming/core-network";
import { isDebugMode } from "../internal-providers";
import { SYSTEM_VERSION } from "../version";

export function createCommonHeaderInterceptor() {
  return {
    onFulfilled: (request: NormalizedRequest): NormalizedRequest => ({
      ...request,
      headers: {
        ...request.headers,
        "X-System-Version": SYSTEM_VERSION,
        "X-Client-Env": isDebugMode() ? "debug" : "release",
      },
    }),
  };
}
