// web-app/src/packages/biz-common/util/src/session-context-store.ts
/**
 * 会话上下文聚合存储 — token + session_id 合一。
 *
 * 三者中 device_id 独立存储（设备生命周期），不在此处：
 *   - device_id → localStorage.__device_id__（device-id-store.ts）
 *   - token + session_id → localStorage.__session_context__（本文件）
 *
 * device_id 与 token/session_id 的生命周期不同：
 *   - device_id 跟随设备，几乎不变，用户未登录时也可能存在
 *   - token + session_id 跟随登录会话，登出/刷新时同步更换
 */

const SESSION_CONTEXT_KEY = "__session_context__";

/** 会话上下文 — 一次登录的凭证信息（不含 device_id） */
export interface SessionContext {
  /** 用户身份令牌（服务端根据 phone 签发） */
  token: string;
  /** token + device_id 组合的会话标识（加密绑定粒度） */
  sessionId: string;
}

/**
 * 获取当前会话上下文。
 * 未初始化时返回 null。
 */
export function getSessionContext(): SessionContext | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SESSION_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.token === "string" && parsed.token) {
      return parsed as SessionContext;
    }
    return null;
  } catch {
    // 解析失败 → 清理脏数据
    localStorage.removeItem(SESSION_CONTEXT_KEY);
    return null;
  }
}

/**
 * 获取当前 token。
 */
export function getToken(): string | null {
  return getSessionContext()?.token ?? null;
}

/**
 * 获取当前 session_id。
 */
export function getSessionId(): string | null {
  return getSessionContext()?.sessionId ?? null;
}

/**
 * 保存会话上下文（原子写入，token + session_id 同时生效）。
 */
export function setSessionContext(ctx: SessionContext): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(SESSION_CONTEXT_KEY, JSON.stringify(ctx));
}

/**
 * 清除会话上下文（登出 / 重新签发时调用）。
 * 注意：不清除 device_id，设备身份独立存在。
 */
export function clearSessionContext(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(SESSION_CONTEXT_KEY);
}
