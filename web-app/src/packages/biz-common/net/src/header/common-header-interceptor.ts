// src/packages/biz-common/net/src/header/common-header-interceptor.ts
/**
 * 公共请求头拦截器 —— 每次请求必须携带的 header。
 *
 * 当前注入：
 *   - X-APP-Version : 系统版本号
 *   - X-Client-Env     : 运行环境（debug / release）
 *   - X-Client-UA      : 浏览器环境摘要
 *   - X-Device-ID      : 设备标识（独立存储，设备生命周期）
 *   - X-Session-ID     : 会话标识（从会话上下文读取）
 */

import type { NormalizedRequest } from "@ming/core-network";
import { collectClientUA, encodeClientUA } from "@ming/core-util";
import { getSessionContext, getDeviceId } from "@ming/biz-common-storage";
import { envCode, clientTypeCode } from "@ming/biz-common-debug";
import { VERSION } from "../../../../../version";

export function createCommonHeaderInterceptor() {
  const clientUA = encodeClientUA(collectClientUA());

  return {
    onFulfilled: (request: NormalizedRequest): NormalizedRequest => {
      const headers: Record<string, string> = {
        ...request.headers,
        "X-App-Version": VERSION.productVersion,
        "X-Client-Env": String(envCode),
        "X-Client-Type": String(clientTypeCode),
        "X-Client-UA": clientUA,
      };

      // device_id：独立存储，设备生命周期（登出后仍存在）
      const deviceId = getDeviceId();
      if (deviceId) {
        headers["X-Device-ID"] = deviceId;
      }

      // session_id：会话上下文，跟随登录状态
      const ctx = getSessionContext();
      if (ctx?.sessionId) {
        headers["X-Session-ID"] = ctx.sessionId;
      }

      return {
        ...request,
        headers,
      };
    },
  };
}
