// web-app/src/packages/features/encryption/src/api/encryption.api.ts
/**
 * 加密密钥交换的原始 HTTP 调用。
 *
 * 使用 netClient（/api/encryption 路径已加入加密白名单，不会递归加密）。
 *
 * @internal
 */
import { netClient } from "@ming/biz-common-net-api";
import type { BizResult } from "@ming/biz-common-net-api";
import { createLogger } from "@ming/core-log";
import type { PublicKeyResponse, SessionResponse } from "./types";

const log = createLogger("encryption/api");

/** 获取服务端 RSA 公钥 */
export async function fetchPublicKey(): Promise<BizResult<PublicKeyResponse>> {
  log.debug("请求服务端 RSA 公钥");
  return netClient.get<PublicKeyResponse>("/api/encryption/key/v1");
}

/** 注册会话 —— 将 RSA 加密后的 AES 密钥发送给服务端 */
export async function registerSession(
  encryptedKeyB64: string,
): Promise<BizResult<SessionResponse>> {
  log.debug("注册加密会话");
  return netClient.post<SessionResponse>("/api/encryption/session/v1", {
    encryptedAesKey: encryptedKeyB64,
  });
}
