// web-app/src/packages/biz-common/net/src/encryption/encryption-crypto.ts
/**
 * 加密业务层封装 — 在 core/encryption 纯原语基础上添加：
 *   - JSON 序列化/反序列化
 *   - Base64 编码
 *   - keyId（会话标识）
 *
 * 纯算法原语在 @ming/core-encryption，这里只负责协议组装。
 */

import type { EncryptedResult, SessionKey } from "./encryption-types";
import { aesEncrypt, aesDecrypt } from "@ming/core-encryption";

// ---------------------------------------------------------------------------
// JSON 加密封装
// ---------------------------------------------------------------------------

/**
 * 将明文字符串加密为 EncryptedResult。
 */
export async function encryptJson(
  jsonStr: string,
  session: SessionKey,
): Promise<EncryptedResult> {
  const plaintext = new TextEncoder().encode(jsonStr);
  const { nonce, ciphertext } = await aesEncrypt(plaintext, session.aesKey);
  return {
    encrypted: _arrayBufferToBase64(ciphertext),
    nonce: _arrayBufferToBase64(nonce),
    keyId: session.keyId,
  };
}

/**
 * 将 EncryptedResult 解密为明文字符串。
 */
export async function decryptPayload(
  payload: EncryptedResult,
  aesKey: CryptoKey,
): Promise<string> {
  const nonce = new Uint8Array(_base64ToArrayBuffer(payload.nonce));
  const ciphertext = new Uint8Array(_base64ToArrayBuffer(payload.encrypted));
  const plaintext = await aesDecrypt(nonce, ciphertext, aesKey);
  return new TextDecoder().decode(plaintext);
}

// ---------------------------------------------------------------------------
// Base64 工具
// ---------------------------------------------------------------------------

function _arrayBufferToBase64(buffer: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < buffer.byteLength; i++) {
    binary += String.fromCharCode(buffer[i]);
  }
  return btoa(binary);
}

function _base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
