// web-app/src/packages/biz-common/util/src/encryption-session-store.ts
/**
 * 加密会话本地存储 —— 密钥交换后由 bootstrap 写入，加密拦截器读取。
 *
 * 与 token / session_id / device_id 一致，使用 localStorage 持久化。
 * 存储时 AES CryptoKey 导出为原始字节（hex 编码），
 * 读取时通过 WebCrypto importKey 重建 CryptoKey 对象。
 *
 * 选择 localStorage 而非 zustand store 的原因：
 *   biz-common/net 拦截器不能依赖 @ming/store（循环依赖：net → store → net-api → net），
 *   而 biz-common/util 已经是 net 的依赖，打破循环。
 */

import { importAesKey, bytesToHex } from "@ming/core-encryption";

/**
 * 加密会话 —— 本地定义，避免 biz-common-util → biz-common-net-api 的循环依赖。
 * 与 @ming/biz-common-net-api 的 EncryptionSession 结构兼容（TypeScript 结构化类型）。
 */
export interface EncryptionSession {
  keyId: string;
  aesKey: CryptoKey;
  signatureKeyHex: string;
  publicKeyPem: string;
  expiresAt: number;
}

/** hex 字符串 → Uint8Array（core-encryption 只提供 bytesToHex，反向转换内联在此） */
function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

const ENCRYPTION_SESSION_KEY = "__encryption_session__";

/** 可序列化的加密会话（AES 密钥以 hex 存储原始字节） */
interface StorableEncryptionSession {
  keyId: string;
  aesKeyRawHex: string;
  signatureKeyHex: string;
  publicKeyPem: string;
  expiresAt: number;
}

/**
 * 将 EncryptionSession 写入 localStorage。
 * AES CryptoKey 导出为原始字节后以 hex 编码存储。
 */
export async function setEncryptionSession(
  session: EncryptionSession,
): Promise<void> {
  if (typeof window === "undefined") return;
  const rawKeyBuffer = await crypto.subtle.exportKey("raw", session.aesKey);
  const storable: StorableEncryptionSession = {
    keyId: session.keyId,
    aesKeyRawHex: bytesToHex(new Uint8Array(rawKeyBuffer)),
    signatureKeyHex: session.signatureKeyHex,
    publicKeyPem: session.publicKeyPem,
    expiresAt: session.expiresAt,
  };
  localStorage.setItem(ENCRYPTION_SESSION_KEY, JSON.stringify(storable));
}

/**
 * 从 localStorage 读取加密会话，重建 CryptoKey。
 * 不存在或已过期时返回 null（过期自动清除）。
 */
export async function getEncryptionSession(): Promise<EncryptionSession | null> {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(ENCRYPTION_SESSION_KEY);
    if (!raw) return null;
    const storable = JSON.parse(raw) as StorableEncryptionSession;
    if (Date.now() >= storable.expiresAt) {
      clearEncryptionSession();
      return null;
    }
    const aesKey = await importAesKey(hexToBytes(storable.aesKeyRawHex));
    return {
      keyId: storable.keyId,
      aesKey,
      signatureKeyHex: storable.signatureKeyHex,
      publicKeyPem: storable.publicKeyPem,
      expiresAt: storable.expiresAt,
    };
  } catch {
    clearEncryptionSession();
    return null;
  }
}

/** 清除加密会话（密钥过期或重新交换时调用）。 */
export function clearEncryptionSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ENCRYPTION_SESSION_KEY);
}
