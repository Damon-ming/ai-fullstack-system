// web-app/src/packages/biz-common/storage/src/encryption-store.ts
/**
 * 加密会话本地存储 —— 密钥交换后由 bootstrap 写入，加密拦截器读取。
 *
 * AES CryptoKey 导出为原始字节（hex 编码），
 * 读取时通过 WebCrypto importKey 重建 CryptoKey 对象。
 */

import { importAesKey, bytesToHex, hexToBytes } from "@ming/core-encryption";
import { getJson, setJson, remove } from "@ming/core-storage";

export interface EncryptionSession {
  keyId: string;
  aesKey: CryptoKey;
  signatureKeyHex: string;
  publicKeyPem: string;
  expiresAt: number;
}

const ENCRYPTION_SESSION_KEY = "__encryption_session__";

interface StorableEncryptionSession {
  keyId: string;
  aesKeyRawHex: string;
  signatureKeyHex: string;
  publicKeyPem: string;
  expiresAt: number;
}

export async function setEncryptionSession(
  session: EncryptionSession,
): Promise<void> {
  // SECURITY: P1-15 AES 密钥以 raw hex 明文存 localStorage。
  // XSS 可读取后解密全部加密通信 / 伪造签名。
  // 当前依赖 React 默认 XSS 防护 + nginx CSP（预留，等 HTTPS 部署时启用）。
  // 上公网时评估 non-extractable CryptoKey（extractable=false）+ 每次刷新重交换密钥，
  // 但需处理多 tab 断连 / 服务端 session 膨胀 / 离线不可用等副作用。
  const rawKeyBuffer = await crypto.subtle.exportKey("raw", session.aesKey);
  const storable: StorableEncryptionSession = {
    keyId: session.keyId,
    aesKeyRawHex: bytesToHex(new Uint8Array(rawKeyBuffer)),
    signatureKeyHex: session.signatureKeyHex,
    publicKeyPem: session.publicKeyPem,
    expiresAt: session.expiresAt,
  };
  setJson(ENCRYPTION_SESSION_KEY, storable);
}

export async function getEncryptionSession(): Promise<EncryptionSession | null> {
  try {
    const storable = getJson<StorableEncryptionSession>(ENCRYPTION_SESSION_KEY);
    if (!storable) return null;
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

export function clearEncryptionSession(): void {
  remove(ENCRYPTION_SESSION_KEY);
}
