// web-app/src/packages/biz-common/net/src/encryption/encryption-types.ts
/**
 * 加密协议类型 — 属于业务/协议层，从 core/encryption 分离出来。
 *
 * core/encryption 只负责纯加密原语（AES-GCM / RSA-OAEP 算法调用）。
 * 版本号、协议 DTO、会话状态等协议层职责放在这里。
 */

// ---------------------------------------------------------------------------
// 版本号
// ---------------------------------------------------------------------------

/**
 * 加密协议版本号 — 当前协议版本
 *
 * 协议变更时递增（如算法升级、签名方案变更），
 * 客户端通过 X-Encrypt-Version header 告知服务端，
 * 服务端据此做版本分发或兼容处理。
 */
export const ENCRYPTION_VERSION = "v1";

/**
 * 签名协议版本号 — 当前签名算法版本
 *
 * 签名方案变更时递增（如 HMAC 算法升级、签名内容格式变更），
 * 客户端在建立会话后调用 GET /api/encryption/signature/v1 获取服务端版本，
 * 与本地版本比对，不一致时提示升级。
 */
export const SIGNATURE_VERSION = "v1";

// ---------------------------------------------------------------------------
// 协议 DTO
// ---------------------------------------------------------------------------

/** JSON 加密结果的 base64 编码形式 — encryptJson 的返回类型 */
export interface EncryptedResult {
  encrypted: string; // base64
  nonce: string; // base64
  keyId: string;
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

/**
 * 会话密钥 — encryptJson 所需的最低密钥信息
 */
export interface SessionKey {
  keyId: string;
  aesKey: CryptoKey;
}
