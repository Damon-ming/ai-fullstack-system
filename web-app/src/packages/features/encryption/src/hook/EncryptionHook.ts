// web-app/src/packages/features/encryption/src/hook/EncryptionHook.ts
/**
 * 加密密钥交换编排。
 *
 * 协议：
 *   1. 获取服务端 RSA 公钥
 *   2. 生成 AES-256 密钥，用 RSA 公钥加密
 *   3. 注册会话，获取 keyId
 *   4. 返回 EncryptionSession
 */
import { createLogger } from "@ming/core-log";
import {
  generateAesKey,
  importRsaPublicKey,
  rsaEncrypt,
  bytesToBase64,
} from "@ming/core-encryption";
import type { EncryptionSession } from "@ming/biz-common-net-api";
import { fetchPublicKey, registerSession } from "../api";

const log = createLogger("encryption/hook");

/** 执行密钥交换，返回加密会话 */
export async function exchangeKeys(): Promise<EncryptionSession> {
  // 1. 获取服务端 RSA 公钥
  const { publicKey: publicKeyPem } = await fetchPublicKey();

  // 2. 生成 AES-256 密钥，用 RSA 公钥加密
  const { rawKeyBytes, cryptoKey } = await generateAesKey();
  const rsaKey = await importRsaPublicKey(publicKeyPem);
  const encryptedAesKey = await rsaEncrypt(rawKeyBytes, rsaKey);
  const encryptedKeyB64 = bytesToBase64(encryptedAesKey);

  // 3. 注册会话，获取 keyId
  const sessionRes = await registerSession(encryptedKeyB64);

  // 4. 构造会话（预留 5 分钟缓冲）
  return {
    keyId: sessionRes.keyId,
    aesKey: cryptoKey,
    publicKeyPem,
    expiresAt: Date.now() + (sessionRes.expiresIn - 300) * 1000,
  };
}
