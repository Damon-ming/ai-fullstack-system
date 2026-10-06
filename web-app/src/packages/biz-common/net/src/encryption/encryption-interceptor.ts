// web-app/src/packages/biz-common/net/src/encryption/encryption-interceptor.ts
/**
 * 加密拦截器装配 — 属于 biz-common/net 层
 *
 * 依赖方向（全部向下，无反向）：
 *   @ming/core-encryption ← net ← net-api ← feature
 *   @ming/core-network    ← net ← net-api ← feature
 *
 * 密钥交换所需的 HTTP 调用通过注入的 get/post 函数提供，
 * 本模块不持有任何实例引用。
 */

import type { InterceptorConfig } from "@ming/core-network";
import {
  generateAesKey,
  importRsaPublicKey,
  rsaEncrypt,
  encryptJson,
  decryptPayload,
} from "@ming/core-encryption";
import type {
  EncryptedPayload,
  EncryptionSession,
  PublicKeyResponse,
  SessionResponse,
} from "@ming/core-encryption";

// ---------------------------------------------------------------------------
// netClient 的函数签名类型（不引用实例，只描述形状）
// ---------------------------------------------------------------------------

type GetFn = <T = unknown>(
  url: string,
) => Promise<[unknown, { data?: T } | null]>;

type PostFn = <T = unknown>(
  url: string,
  data?: unknown,
) => Promise<[unknown, { data?: T } | null]>;

// ---------------------------------------------------------------------------
// 工厂函数：注入 get/post → 返回拦截器对
// ---------------------------------------------------------------------------

export function createEncryptionInterceptors(get: GetFn, post: PostFn): {
  requestEncrypt: InterceptorConfig;
  responseDecrypt: InterceptorConfig;
} {
  let currentSession: EncryptionSession | null = null;
  let sessionPromise: Promise<EncryptionSession> | null = null;

  // ---- 密钥交换 -------------------------------------------------------

  async function getSession(): Promise<EncryptionSession> {
    if (currentSession && Date.now() < currentSession.expiresAt) {
      return currentSession;
    }
    if (!sessionPromise) {
      sessionPromise = (async () => {
        try {
          const publicKey = await fetchPublicKey();
          const session = await createSession(publicKey);
          currentSession = session;
          return session;
        } finally {
          sessionPromise = null;
        }
      })();
    }
    return sessionPromise;
  }

  async function fetchPublicKey(): Promise<string> {
    const [err, res] = await get<PublicKeyResponse>("/api/encryption/key");
    if (err || !res?.data?.publicKey) {
      throw new Error(`Failed to fetch public key`);
    }
    return res.data.publicKey;
  }

  async function createSession(publicKeyPem: string): Promise<EncryptionSession> {
    const { rawKeyBytes, cryptoKey } = await generateAesKey();
    const rsaKey = await importRsaPublicKey(publicKeyPem);
    const encryptedAesKey = await rsaEncrypt(rawKeyBytes, rsaKey);
    const encryptedKeyB64 = bytesToBase64(encryptedAesKey);

    const [err, res] = await post<SessionResponse>(
      "/api/encryption/session",
      { encryptedAesKey: encryptedKeyB64 },
    );
    if (err || !res?.data?.keyId) {
      throw new Error(`Session registration failed`);
    }

    return {
      keyId: res.data.keyId,
      aesKey: cryptoKey,
      publicKeyPem,
      expiresAt: Date.now() + (res.data.expiresIn - 300) * 1000,
    };
  }

  // ---- 请求拦截器 -----------------------------------------------------

  const requestEncrypt: InterceptorConfig = {
    onFulfilled: async (request) => {
      const contentType = request.headers["content-type"] || "";
      if (!contentType.includes("application/json")) return request;
      if (request.data instanceof FormData) return request;
      if (typeof request.data !== "object" || request.data === null) return request;
      if (isEncryptedPayload(request.data)) return request;

      if (
        request.url?.includes("/api/encryption/key") ||
        request.url?.includes("/api/encryption/session")
      ) {
        return request;
      }

      try {
        const session = await getSession();
        const jsonStr = JSON.stringify(request.data);
        const encrypted = await encryptJson(jsonStr, session.aesKey, session.keyId);
        return {
          ...request,
          data: encrypted,
          headers: {
            ...request.headers,
            "x-encrypt-enabled": "1",
          },
        };
      } catch (error) {
        console.warn("[Encryption] 请求加密失败，降级为明文:", error);
        return request;
      }
    },
  };

  // ---- 响应拦截器 -----------------------------------------------------

  const responseDecrypt: InterceptorConfig = {
    onFulfilled: async (response) => {
      if (response.headers["content-type"]?.includes("text/event-stream")) {
        return response;
      }

      const url = response.config?.url || "";
      if (
        url.includes("/api/encryption/key") ||
        url.includes("/api/encryption/session")
      ) {
        return response;
      }

      if (!isEncryptedPayload(response.data)) return response;

      try {
        const session = await getSession();
        const decryptedStr = await decryptPayload(
          response.data as EncryptedPayload,
          session.aesKey,
        );
        return {
          ...response,
          data: JSON.parse(decryptedStr),
        };
      } catch (error) {
        console.warn("[Encryption] 响应解密失败，返回原始数据:", error);
        return response;
      }
    },
    onRejected: async (error) => {
      const status = error?.status || error?.response?.status;
      if (status === 40101 || status === 401) {
        console.info("[Encryption] 会话过期，刷新中...");
        currentSession = null;
        sessionPromise = null;
      }
      throw error;
    },
  };

  return { requestEncrypt, responseDecrypt };
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function isEncryptedPayload(data: unknown): data is EncryptedPayload {
  return (
    typeof data === "object" &&
    data !== null &&
    typeof (data as EncryptedPayload).encrypted === "string" &&
    typeof (data as EncryptedPayload).nonce === "string" &&
    typeof (data as EncryptedPayload).keyId === "string"
  );
}
