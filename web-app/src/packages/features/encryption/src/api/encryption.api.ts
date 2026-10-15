// web-app/src/packages/features/encryption/src/api/encryption.api.ts
/**
 * 加密密钥交换的原始 HTTP 调用。
 *
 * 使用 netClient（/api/encryption 路径已加入加密白名单，不会递归加密）。
 *
 * @internal
 */
import { netClient } from "@ming/biz-common-net-api";
import { createLogger } from "@ming/core-log";
import type { PublicKeyResponse, SessionResponse } from "./types";

const log = createLogger("encryption/api");

/** 获取服务端 RSA 公钥 */
export async function fetchPublicKey(): Promise<PublicKeyResponse> {
  log.debug("请求服务端 RSA 公钥");
  const [err, resp] = await netClient.get<PublicKeyResponse>(
    "/api/encryption/key/v1",
  );
  if (err || !resp?.data) {
    throw new Error(`获取公钥失败: ${err?.clientData?.message || "未知错误"}`);
  }
  return resp.data;
}

/** 注册会话 —— 将 RSA 加密后的 AES 密钥发送给服务端 */
export async function registerSession(
  encryptedKeyB64: string,
): Promise<SessionResponse> {
  log.debug("注册加密会话");
  const [err, resp] = await netClient.post<SessionResponse>(
    "/api/encryption/session/v1",
    { encryptedAesKey: encryptedKeyB64 },
  );
  if (err || !resp?.data) {
    throw new Error(`会话注册失败: ${err?.clientData?.message || "未知错误"}`);
  }
  return resp.data;
}
