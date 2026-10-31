// web-app/src/packages/biz-common/storage/src/auth-store.ts
/**
 * 认证态本地存储 —— 设备 ID + 会话上下文（token + session_id）。
 *
 * 生命周期：
 *   - device_id 跟随设备，几乎不变，未登录时也可能存在
 *   - token + session_id 跟随登录会话，登出/刷新时同步更换
 *
 * 两者均在 initDeviceToken 中由 hook 层编排写入。
 */

import { getJson, setJson, remove, get, set } from "@ming/core-storage";

// ---------------------------------------------------------------------------
// 设备 ID（独立存储，设备生命周期）
// ---------------------------------------------------------------------------

const DEVICE_ID_KEY = "__device_id__";

export function getDeviceId(): string | null {
  return get(DEVICE_ID_KEY);
}

export function setDeviceId(deviceId: string): void {
  set(DEVICE_ID_KEY, deviceId);
}

export function clearDeviceId(): void {
  remove(DEVICE_ID_KEY);
}

// ---------------------------------------------------------------------------
// 会话上下文（token + session_id 原子读写）
// ---------------------------------------------------------------------------

// SECURITY: 存储在 localStorage，同域 JS 可读（P1-14）。
// XSS 漏洞可直接窃取 token → 防御重心是防 XSS（react-markdown v9 默认转义 HTML +
// 无第三方脚本 + 内部部署，XSS 攻击面小）。token TTL 90 天硬上限限制泄露窗口。
// 上公网 + HTTPS 时评估迁移到 HttpOnly Cookie。
const SESSION_CONTEXT_KEY = "__session_context__";

export interface SessionContext {
  token: string;
  sessionId: string;
}

export function getSessionContext(): SessionContext | null {
  const parsed = getJson<SessionContext>(SESSION_CONTEXT_KEY);
  if (parsed && typeof parsed.token === "string" && parsed.token) {
    return parsed;
  }
  return null;
}

export function getToken(): string | null {
  return getSessionContext()?.token ?? null;
}

export function getSessionId(): string | null {
  return getSessionContext()?.sessionId ?? null;
}

export function setSessionContext(ctx: SessionContext): void {
  setJson(SESSION_CONTEXT_KEY, ctx);
}

export function clearSessionContext(): void {
  remove(SESSION_CONTEXT_KEY);
}
