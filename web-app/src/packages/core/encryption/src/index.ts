// web-app/src/packages/core/encryption/src/index.ts
/**
 * @ming/core-encryption — 零依赖的加密原语模块
 *
 * 职责：提供 AES-GCM / RSA-OAEP 底层加解密能力 + 协议数据结构。
 * 不含任何网络、拦截器、业务逻辑 —— 可被任何上层模块安全引用。
 */

export type {
  EncryptedPayload,
  PublicKeyResponse,
  SessionResponse,
  EncryptionSession,
} from "./types";

export {
  generateAesKey,
  importAesKey,
  aesEncrypt,
  aesDecrypt,
  importRsaPublicKey,
  rsaEncrypt,
  encryptJson,
  decryptPayload,
} from "./crypto-engine";
