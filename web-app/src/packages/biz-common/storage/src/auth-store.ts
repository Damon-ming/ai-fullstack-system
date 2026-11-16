// web-app/src/packages/biz-common/storage/src/auth-store.ts
/**
 * 认证态本地存储 —— 每台设备一个会话 token。
 */

import { get, set, remove } from "@ming/core-storage";

// ---------------------------------------------------------------------------
// 会话凭据
// ---------------------------------------------------------------------------

// SECURITY: 存储在 localStorage，同域 JS 可读（P1-14）。
// XSS 漏洞可直接窃取 token → 防御重心是防 XSS（react-markdown v9 默认转义 HTML +
// 无第三方脚本 + 内部部署，XSS 攻击面小）。服务端按 7 天闲置时间失效。
// 上公网 + HTTPS 时评估迁移到 HttpOnly Cookie。
const AUTH_TOKEN_KEY = "__auth_token__";

export function getStoredToken(): string | null {
  return get(AUTH_TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  set(AUTH_TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  remove(AUTH_TOKEN_KEY);
}
