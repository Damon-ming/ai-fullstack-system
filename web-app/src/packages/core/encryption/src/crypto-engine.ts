// web-app/src/packages/core/encryption/src/crypto-engine.ts
/**
 * WebCrypto 底层封装
 *
 * - AES-GCM 加解密（浏览器原生 SubtleCrypto）
 * - RSA-OAEP 加密（仅用于加密 AES 密钥发给服务端）
 *
 * 注意：TypeScript 5.7+ 的 DOM lib 对 BufferSource 做了严格区分，
 * Uint8Array<ArrayBufferLike> 不再自动赋值给 BufferSource，
 * 需要通过 buffer 切片确保类型为 ArrayBuffer 后端。
 */

import type { EncryptedPayload } from "./types";

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const AES_NONCE_SIZE = 12; // GCM 推荐 96 bit

// ---------------------------------------------------------------------------
// 类型工具：确保 Uint8Array 基于 ArrayBuffer（兼容 TS 5.7 严格 BufferSource）
// ---------------------------------------------------------------------------

/** 将 Uint8Array 转为 BufferSource 兼容格式（强制 ArrayBuffer 后端） */
function toBufferSource(data: Uint8Array): ArrayBuffer {
  // 创建副本确保 buffer 是纯 ArrayBuffer（不是 SharedArrayBuffer）
  return data.buffer.slice(
    data.byteOffset,
    data.byteOffset + data.byteLength,
  ) as ArrayBuffer;
}

// ---------------------------------------------------------------------------
// AES-GCM 操作
// ---------------------------------------------------------------------------

/**
 * 生成 AES-256 原始密钥字节，并导入为 WebCrypto CryptoKey。
 * 返回 { rawKeyBytes, cryptoKey } —— rawKeyBytes 用于 RSA 加密传输。
 */
export async function generateAesKey(): Promise<{
  rawKeyBytes: Uint8Array;
  cryptoKey: CryptoKey;
}> {
  const cryptoKey = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true, // extractable — 我们需要导出原始字节给 RSA 加密
    ["encrypt", "decrypt"],
  );
  const rawKeyBuffer = await crypto.subtle.exportKey("raw", cryptoKey);
  return {
    rawKeyBytes: new Uint8Array(rawKeyBuffer),
    cryptoKey,
  };
}

/**
 * 从原始 AES 密钥字节导入 CryptoKey。
 */
export async function importAesKey(
  rawKeyBytes: Uint8Array,
): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    toBufferSource(rawKeyBytes),
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

/**
 * AES-GCM 加密。
 * 返回 { nonce, ciphertext }（ciphertext 已含 16 字节认证标签）。
 */
export async function aesEncrypt(
  plaintext: Uint8Array,
  cryptoKey: CryptoKey,
  aad?: Uint8Array,
): Promise<{ nonce: Uint8Array; ciphertext: Uint8Array }> {
  const nonce = crypto.getRandomValues(new Uint8Array(AES_NONCE_SIZE));
  const algo: AesGcmParams = { name: "AES-GCM", iv: toBufferSource(nonce) };
  if (aad) algo.additionalData = toBufferSource(aad);

  const ctBuffer = await crypto.subtle.encrypt(
    algo,
    cryptoKey,
    toBufferSource(plaintext),
  );
  return {
    nonce,
    ciphertext: new Uint8Array(ctBuffer),
  };
}

/**
 * AES-GCM 解密。
 * 认证失败会 reject。
 */
export async function aesDecrypt(
  nonce: Uint8Array,
  ciphertext: Uint8Array,
  cryptoKey: CryptoKey,
  aad?: Uint8Array,
): Promise<Uint8Array> {
  const algo: AesGcmParams = { name: "AES-GCM", iv: toBufferSource(nonce) };
  if (aad) algo.additionalData = toBufferSource(aad);

  const ptBuffer = await crypto.subtle.decrypt(
    algo,
    cryptoKey,
    toBufferSource(ciphertext),
  );
  return new Uint8Array(ptBuffer);
}

// ---------------------------------------------------------------------------
// RSA-OAEP 操作（仅用于加密 AES 密钥）
// ---------------------------------------------------------------------------

/**
 * 导入 PEM 格式 RSA 公钥 → CryptoKey。
 */
export async function importRsaPublicKey(pem: string): Promise<CryptoKey> {
  const pemBody = pem
    .replace(/-----BEGIN PUBLIC KEY-----/, "")
    .replace(/-----END PUBLIC KEY-----/, "")
    .replace(/\s/g, "");
  const binaryDer = base64ToArrayBuffer(pemBody);

  return crypto.subtle.importKey(
    "spki",
    binaryDer,
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  );
}

/**
 * 用 RSA-OAEP 公钥加密数据（客户端 → 服务端：加密 AES 密钥）。
 */
export async function rsaEncrypt(
  data: Uint8Array,
  publicKey: CryptoKey,
): Promise<Uint8Array> {
  const ctBuffer = await crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    publicKey,
    toBufferSource(data),
  );
  return new Uint8Array(ctBuffer);
}

// ---------------------------------------------------------------------------
// 高层封装：JSON 字符串 ↔ EncryptedPayload
// ---------------------------------------------------------------------------

/**
 * 将明文字符串加密为 EncryptedPayload。
 */
export async function encryptJson(
  jsonStr: string,
  cryptoKey: CryptoKey,
  keyId: string,
): Promise<EncryptedPayload> {
  const plaintext = new TextEncoder().encode(jsonStr);
  const { nonce, ciphertext } = await aesEncrypt(plaintext, cryptoKey);
  return {
    encrypted: arrayBufferToBase64(ciphertext),
    nonce: arrayBufferToBase64(nonce),
    keyId,
  };
}

/**
 * 将 EncryptedPayload 解密为明文字符串。
 */
export async function decryptPayload(
  payload: EncryptedPayload,
  cryptoKey: CryptoKey,
): Promise<string> {
  const nonce = new Uint8Array(base64ToArrayBuffer(payload.nonce));
  const ciphertext = new Uint8Array(base64ToArrayBuffer(payload.encrypted));
  const plaintext = await aesDecrypt(nonce, ciphertext, cryptoKey);
  return new TextDecoder().decode(plaintext);
}

// ---------------------------------------------------------------------------
// Base64 工具
// ---------------------------------------------------------------------------

function arrayBufferToBase64(buffer: Uint8Array): string {
  let binary = "";
  const len = buffer.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(buffer[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
