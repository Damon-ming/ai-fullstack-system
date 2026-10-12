// src/packages/biz-common/net/src/header/common-header-interceptor.ts
/**
 * 公共请求头拦截器 —— 每次请求必须携带的 header。
 *
 * 当前注入：
 *   - X-System-Version : 系统版本号
 *   - X-Client-Env     : 运行环境（debug / release）
 *   - X-Client-UA      : 浏览器环境摘要（UA + 语言 + 平台 + 分辨率 + 时区）
 *
 * 注：加密协议相关 header（X-Encrypt-Version / X-Signature-Version）
 * 由 encryption-interceptor 管理，仅在加密启用时注入。
 */

import type { NormalizedRequest } from "@ming/core-network";
import { collectClientUA, encodeClientUA } from "@ming/core-util";
import { getDeviceId } from "@ming/biz-common-util";
import { isDebugMode } from "../internal-providers";
import { SYSTEM_VERSION } from "../version";

// ---------------------------------------------------------------------------
// 拦截器
// ---------------------------------------------------------------------------

export function createCommonHeaderInterceptor() {
  // 浏览器信息在启动时一次性采集（不会变化），避免每次请求重复序列化
  const clientUA = encodeClientUA(collectClientUA());

  return {
    onFulfilled: (request: NormalizedRequest): NormalizedRequest => ({
      ...request,
      headers: {
        ...request.headers,
        "X-System-Version": SYSTEM_VERSION,
        "X-Client-Env": isDebugMode() ? "debug" : "release",
        "X-Client-UA": clientUA,
        ...(getDeviceId() ? { "X-Device-ID": getDeviceId()! } : {}),
      },
    }),
  };
}
