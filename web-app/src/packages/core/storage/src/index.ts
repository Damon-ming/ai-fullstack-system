// src/packages/core/storage/src/index.ts
/**
 * 本地存储纯技术封装 —— 业务无关，SSR 安全。
 *
 * 收口项目中所有 localStorage 调用，提供：
 *   - get / set / remove —— 原始字符串读写
 *   - getJson / setJson —— JSON 自动序列化（含 try/catch）
 *
 * 消费方：biz-common/util、features/account、features/history
 */

/** SSR 安全守卫：服务端环境返回 null/no-op */
const isBrowser = (): boolean => typeof window !== "undefined";

export function get(key: string): string | null {
  if (!isBrowser()) return null;
  return localStorage.getItem(key);
}

export function set(key: string, value: string): void {
  if (!isBrowser()) return;
  localStorage.setItem(key, value);
}

export function remove(key: string): void {
  if (!isBrowser()) return;
  localStorage.removeItem(key);
}

export function getJson<T>(key: string): T | null {
  if (!isBrowser()) return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    // 解析失败 → 清理脏数据
    localStorage.removeItem(key);
    return null;
  }
}

export function setJson<T>(key: string, value: T): void {
  if (!isBrowser()) return;
  localStorage.setItem(key, JSON.stringify(value));
}
