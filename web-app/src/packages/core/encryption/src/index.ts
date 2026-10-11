// web-app/src/packages/core/encryption/src/index.ts
/**
 * @ming/core-encryption — 零依赖的加密原语模块
 *
 * 职责：提供 AES-GCM / RSA-OAEP 底层加解密能力。
 * 不含 JSON 序列化、base64 编码、版本号、协议 DTO、会话状态、网络、拦截器、业务逻辑。
 * 可直接移植到任何需要 WebCrypto AES-GCM / RSA-OAEP 的项目。
 */

export {
  generateAesKey,
  importAesKey,
  aesEncrypt,
  aesDecrypt,
  importRsaPublicKey,
  rsaEncrypt,
  bytesToBase64,
} from "./crypto-engine";

export {
  generateNonce,
  hmacSha256,
} from "./signature";
