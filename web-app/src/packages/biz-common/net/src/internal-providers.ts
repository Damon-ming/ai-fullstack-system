// web-app/src/packages/biz-common/net/src/internal-providers.ts
/**
 * 内部提供者 —— 模块级变量，由 bootstrap 注入。
 *
 * 拦截器通过这里读取 store 数据，避免直接 import @ming/store，
 * 切断 biz-common/net → store 的反向依赖。
 */
import type { EncryptionSession } from "./encryption/encryption-types";

// ---------------------------------------------------------------------------
// 加密会话
// ---------------------------------------------------------------------------

type SessionGetter = () => EncryptionSession | null;

let _getSession: SessionGetter | null = null;

export function setEncryptionSessionGetter(fn: SessionGetter): void {
  _getSession = fn;
}

export function getEncryptionSession(): EncryptionSession | null {
  return _getSession?.() ?? null;
}

// ---------------------------------------------------------------------------
// 设备 Token
// ---------------------------------------------------------------------------

type TokenGetter = () => string | null;

let _getToken: TokenGetter | null = null;

export function setTokenGetter(fn: TokenGetter): void {
  _getToken = fn;
}

export function getToken(): string | null {
  return _getToken?.() ?? null;
}

// ---------------------------------------------------------------------------
// Debug 模式
// ---------------------------------------------------------------------------

type DebugGetter = () => boolean;

let _isDebug: DebugGetter | null = null;

export function setDebugGetter(fn: DebugGetter): void {
  _isDebug = fn;
}

export function isDebugMode(): boolean {
  return _isDebug?.() ?? false;
}
