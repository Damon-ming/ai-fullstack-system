/**
 * 加密密钥交换编排。
 *
 * 协议：
 *   1. 获取服务端 RSA 公钥
 *   2. 生成 AES-256 密钥，用 RSA 公钥加密
 *   3. HKDF 派生签名密钥（从 AES 主密钥）
 *   4. 注册会话，获取 keyId
 *   5. 返回 EncryptionSession（含派生后的签名密钥）
 */
import { createLogger } from "@ming/core-log";
import {
  generateAesKey,
  importAesKey,
  importRsaPublicKey,
  rsaEncrypt,
  bytesToBase64,
  bytesToHex,
  deriveKeyMaterial,
} from "@ming/core-encryption";
import type { EncryptionSession } from "@ming/biz-common-net-api";
import { fetchPublicKey, registerSession } from "../api";

const log = createLogger("encryption/hook");

/**
 * HKDF 签名密钥派生上下文（前后端必须一致）。
 *
 * 此常量属于业务协议层，定义在 features/encryption（业务层），
 * 注入到 core/encryption（纯技术层），避免核心模块与项目耦合。
 */
const SIGN_CONTEXT = "ai-fullstack-signature-v1";

/** 执行密钥交换，返回加密会话 */
export async function exchangeKeys(): Promise<EncryptionSession> {
  // 1. 获取服务端 RSA 公钥
  const { publicKey: publicKeyPem } = await fetchPublicKey();

  // 2. 生成 AES-256 密钥，用 RSA 公钥加密
  const { rawKeyBytes } = await generateAesKey();
  const rsaKey = await importRsaPublicKey(publicKeyPem);
  const encryptedAesKey = await rsaEncrypt(rawKeyBytes, rsaKey);
  const encryptedKeyB64 = bytesToBase64(encryptedAesKey);

  // 3. 导入 AES 密钥 + HKDF 派生签名密钥（两个独立密钥，职责分离）
  //    signContext 由业务层注入，core/encryption 不包含该常量
  const encKey = await importAesKey(rawKeyBytes);
  const signKeyBytes = await deriveKeyMaterial(rawKeyBytes, SIGN_CONTEXT);
  const signatureKeyHex = bytesToHex(signKeyBytes);

  // 4. 注册会话，获取 keyId
  const sessionRes = await registerSession(encryptedKeyB64);

  // 5. 构造会话（预留 5 分钟缓冲）
  return {
    keyId: sessionRes.keyId,
    aesKey: encKey,
    signatureKeyHex,
    publicKeyPem,
    expiresAt: Date.now() + (sessionRes.expiresIn - 300) * 1000,
  };
}

