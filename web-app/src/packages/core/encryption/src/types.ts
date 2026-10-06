// web-app/src/packages/core/encryption/src/types.ts

/**
 * 加密载荷结构 — 与后端 EncryptedPayload 对应
 */
export interface EncryptedPayload {
  encrypted: string; // base64
  nonce: string; // base64
  keyId: string;
}

/**
 * 服务端返回的公钥信息
 */
export interface PublicKeyResponse {
  publicKey: string; // PEM 格式
  algorithm: string; // "RSA-OAEP-256"
}

/**
 * 会话注册响应
 */
export interface SessionResponse {
  keyId: string;
  expiresIn: number; // 秒
}

/**
 * 加密会话状态（前端内存中持有）
 */
export interface EncryptionSession {
  keyId: string;
  aesKey: CryptoKey; // WebCrypto AES-GCM key 对象
  publicKeyPem: string; // 服务端 RSA 公钥 PEM
  expiresAt: number; // 时间戳 (ms)
}
