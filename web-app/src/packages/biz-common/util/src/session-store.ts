// web-app/src/packages/biz-common/util/src/session-store.ts
/**
 * 会话 ID 本地存储 —— 服务端下发，客户端缓存并回传。
 *
 * session_id 标识一个 (token + device_id) 的唯一会话组合，
 * 是加密密钥绑定的粒度单位。
 *
 * 服务端每次签发 token 时生成 session_id，
 * 同一 (token, device_id) 组合复用同一 session_id。
 */

const SESSION_ID_KEY = "__session_id__";

/**
 * 获取当前缓存的 session_id。
 * 未初始化时返回 null。
 */
export function getSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(SESSION_ID_KEY);
}

/**
 * 缓存服务端下发的 session_id。
 */
export function setSessionId(sessionId: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(SESSION_ID_KEY, sessionId);
}

/**
 * 清除缓存的 session_id（重新登录时调用）。
 */
export function clearSessionId(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(SESSION_ID_KEY);
}
