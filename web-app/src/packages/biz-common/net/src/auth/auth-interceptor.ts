// web-app/src/packages/biz-common/net/src/auth/auth-interceptor.ts
/**
 * 认证拦截器 —— 注入设备 Token 到 Cookie 头
 *
 * 设计说明：
 *   - 临时方案：token 存 localStorage，通过 Cookie 头发送
 *   - 未来升级：服务端 Set-Cookie 设置 HttpOnly，此拦截器可移除
 *   - Cookie 头格式：Cookie: <token_name>=<device_token>
 *   - 服务端从 Cookie 中解析 token，查白名单 dict 放行
 *
 * HttpOnly 对比：
 *   当前（临时）：token 在 JS 可读，XSS 可窃取
 *   未来（正式）：HttpOnly Cookie，JS 不可读，防御 XSS
 *   本次拦截器在两种方案下都生效（统一注入 Cookie 头）
 */

import type { InterceptorConfig } from "@ming/core-network";
import { getDeviceToken } from "./device-token";

// Cookie 中 token 的 key 名（与服务端约定）
const TOKEN_COOKIE_NAME = "device_auth_token";

export function createAuthInterceptor(): InterceptorConfig {
  return {
    onFulfilled: (request) => {
      const token = getDeviceToken();
      // 注入 Cookie 头（axios / fetch 不会自动注入自定义 Cookie）
      return {
        ...request,
        headers: {
          ...request.headers,
          Cookie: `${TOKEN_COOKIE_NAME}=${token}`,
        },
      };
    },
  };
}
