// web-app/src/packages/biz-common/net/src/encryption/encryption-interceptor.ts
/**
 * 加密 + 签名拦截器装配 — 属于 biz-common/net 层
 *
 * 支持两种请求类型：
 *   1. JSON: 整体签名 → 整体加密
 *   2. FormData (文件上传): 提取 meta_json → 签名 + 加密 meta → 重新组装 FormData
 *
 * 请求头：
 *   X-Encrypt-Enabled: 1       → 服务端对响应也加密
 *   X-Signature: <hex>         → 请求签名
 *   X-Timestamp: <ms>          → 签名时间戳
 *   X-Nonce: <hex>             → 签名随机数
 *
 * 响应流程：
 *   收到密文 → 解密 → 明文 JSON
 */

import type { InterceptorConfig } from "@ming/core-network";
import {
  generateAesKey,
  importRsaPublicKey,
  rsaEncrypt,
  encryptJson,
  decryptPayload,
  generateNonce,
  computeSignature,
} from "@ming/core-encryption";
import type {
  EncryptedPayload,
  EncryptionSession,
  PublicKeyResponse,
  SessionResponse,
} from "@ming/core-encryption";

// ---------------------------------------------------------------------------
// netClient 函数签名
// ---------------------------------------------------------------------------

type GetFn = <T = unknown>(
  url: string,
) => Promise<[unknown, { data?: T } | null]>;

type PostFn = <T = unknown>(
  url: string,
  data?: unknown,
) => Promise<[unknown, { data?: T } | null]>;

// ---------------------------------------------------------------------------
// 工厂函数
// ---------------------------------------------------------------------------

export function createEncryptionInterceptors(
  get: GetFn,
  post: PostFn,
  signatureSecret: string,
): {
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
      throw new Error("Failed to fetch public key");
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
      throw new Error("Session registration failed");
    }

    return {
      keyId: res.data.keyId,
      aesKey: cryptoKey,
      publicKeyPem,
      expiresAt: Date.now() + (res.data.expiresIn - 300) * 1000,
    };
  }

  // ---- 请求拦截器：签名 + 加密 ---------------------------------------

  const requestEncrypt: InterceptorConfig = {
    onFulfilled: async (request) => {
      if (request.url?.includes("/api/encryption/")) return request;

      // FormData：文件上传场景
      if (request.data instanceof FormData) {
        return handleFormData(request);
      }

      // JSON 请求
      const contentType = request.headers["content-type"] || "";
      if (!contentType.includes("application/json")) return request;
      if (typeof request.data !== "object" || request.data === null) return request;
      if (isEncryptedPayload(request.data)) return request;

      return handleJson(request);
    },
  };

  // ---- 响应拦截器：解密 ---------------------------------------------

  const responseDecrypt: InterceptorConfig = {
    onFulfilled: async (response) => {
      if (response.headers["content-type"]?.includes("text/event-stream")) {
        return response;
      }

      const url = response.config?.url || "";
      if (url.includes("/api/encryption/")) {
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

  // ==== 私有 ==========================================================

  /** 处理 JSON 请求：签名 + 加密 */
  async function handleJson(request: {
    data: unknown;
    headers: Record<string, string>;
    [key: string]: unknown;
  }): Promise<unknown> {
    try {
      const signedData = await signParams(request.data as Record<string, unknown>);
      const session = await getSession();
      const jsonStr = JSON.stringify(signedData);
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
      console.warn("[Encryption] JSON 加密失败，降级为明文:", error);
      return request;
    }
  }

  /** 处理 FormData 请求：加密 meta_json + 添加签名字段到 FormData */
  async function handleFormData(request: {
    data: FormData;
    headers: Record<string, string>;
    [key: string]: unknown;
  }): Promise<unknown> {
    try {
      const formData = request.data as FormData;
      const metaJson = formData.get("meta_json") as string | null;
      const meta = metaJson ? JSON.parse(metaJson) : {};

      // 签名
      const timestamp = Date.now();
      const nonce = generateNonce();
      const signature = await computeSignature(meta, signatureSecret, timestamp, nonce);

      // 加密 meta_json
      const session = await getSession();
      const encrypted = await encryptJson(
        JSON.stringify(meta),
        session.aesKey,
        session.keyId,
      );

      // 重新组装 FormData：替换 meta_json 为加密版本，添加签名
      const newFormData = new FormData();
      // 复制所有文件
      formData.forEach((value, key) => {
        if (key !== "meta_json") {
          newFormData.append(key, value);
        }
      });
      newFormData.set("meta_json_encrypted", JSON.stringify(encrypted));
      newFormData.set("timestamp", String(timestamp));
      newFormData.set("nonce", nonce);
      newFormData.set("signature", signature);

      return {
        ...request,
        data: newFormData,
        headers: {
          ...request.headers,
          "x-encrypt-enabled": "1",
        },
      };
    } catch (error) {
      console.warn("[Encryption] FormData 加密失败，降级为明文:", error);
      return request;
    }
  }

  async function signParams(
    params: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const timestamp = Date.now();
    const nonce = generateNonce();
    const signature = await computeSignature(params, signatureSecret, timestamp, nonce);
    return { ...params, timestamp, nonce, signature };
  }
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
