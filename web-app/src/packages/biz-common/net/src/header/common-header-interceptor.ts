// src/packages/biz-common/net/src/header/common-header-interceptor.ts
/**
 * 公共请求头拦截器 —— 每次请求必须携带的 header。
 *
 * 当前注入：
 *   - X-App-Version  : 系统版本号
 *   - X-Client-Env   : 运行环境（debug / release）
 *   - X-Client-Type  : 客户端类型编码
 *   - X-Client-UA    : 浏览器环境摘要
 *   - X-Device-ID    : 设备标识（独立存储，设备生命周期）
 *   - X-Session-ID   : 会话标识（从会话上下文读取）
 *   - X-Language     : 当前语言偏好（服务端据此下发对应 locale 的词条）
 *   - Cookie         : 设备认证 token（从会话上下文读取，有则注入）
 */

import type { NormalizedRequest } from "@ming/core-network";
import { collectClientUA, encodeClientUA } from "@ming/core-util";
import {
  getSessionContext,
  getDeviceId,
  getToken,
} from "@ming/biz-common-storage";
import { envCode, clientTypeCode } from "@ming/biz-common-debug";
import { VERSION } from "../../../../../version";
import { i18n } from "@ming/i18n";

const TOKEN_COOKIE_NAME = "device_auth_token";

export function createCommonHeaderInterceptor() {
  const clientUA = encodeClientUA(collectClientUA());

  return {
    onFulfilled: (request: NormalizedRequest): NormalizedRequest => {
      const headers: Record<string, string> = {
        ...request.headers,
        "X-App-Version": VERSION.productVersion,
        "X-Client-Env": String(envCode()),
        "X-Client-Type": String(clientTypeCode()),
        "X-Client-UA": clientUA,
      };

      // X-Language：当前语言偏好，服务端据此返回对应 locale 的词条
      // 后端 negotiate_locale 支持前缀匹配（zh → zh_CN, en → en_US）
      headers["X-Language"] = i18n.language;

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

      // token：设备认证令牌，有则注入 Cookie 头
      const token = getToken();
      if (token) {
        headers["Cookie"] = `${TOKEN_COOKIE_NAME}=${token}`;
      }

      return {
        ...request,
        headers,
      };
    },
  };
}
