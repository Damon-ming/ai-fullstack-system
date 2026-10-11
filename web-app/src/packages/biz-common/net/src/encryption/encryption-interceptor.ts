// web-app/src/packages/biz-common/net/src/encryption/encryption-interceptor.ts
/**
 * 加密 + 签名拦截器 — 纯加解密，不感知密钥交换。
 *
 * 密钥交换在 bootstrap 阶段由 features-encryption-api 完成，
 * 会话从 app-state 读取。
 *
 * 支持两种请求类型：
 *   1. JSON: 整体签名 → 整体加密
 *   2. FormData (文件上传): 提取 meta_json → 签名 + 加密 meta → 重新组装 FormData
 *
 * 请求头（加密协议层）：
 *   X-Encrypt-Enabled: 1       → 服务端对响应也加密
 *   X-Encrypt-Version: v1      → 客户端加密协议版本
 *   X-Signature-Version: v1    → 客户端签名协议版本
 *   X-Signature: <hex>         → 请求签名
 *   X-Timestamp: <ms>          → 签名时间戳
 *   X-Nonce: <hex>             → 签名随机数
 *
 * 加密 payload 内也携带 version 字段（防篡改，认证后验证）
 *
 * 响应流程：
 *   收到密文 → 解密 → 明文 JSON
 */

import type { InterceptorConfig } from "@ming/core-network";
import { createLogger } from "@ming/core-log";
import { generateNonce } from "@ming/core-encryption";
import { useAppStore } from "@ming/store";
import { encryptJson, decryptPayload } from "./encryption-crypto";
import { computeSignature, signParams } from "./signature";
import type { EncryptedResult, EncryptionSession } from "./encryption-types";
import { ENCRYPTION_VERSION, SIGNATURE_VERSION } from "./encryption-types";

const log = createLogger("net/encryption");

// ---------------------------------------------------------------------------
// 工厂函数
// ---------------------------------------------------------------------------

export function createEncryptionInterceptors(signatureSecret: string): {
  requestEncrypt: InterceptorConfig;
  responseDecrypt: InterceptorConfig;
} {
  // ---- 从 app-state 获取会话 -------------------------------------------

  function getSession(): EncryptionSession | null {
    const session = useAppStore.getState().encryption.session;
    if (!session) return null;
    if (Date.now() >= session.expiresAt) {
      useAppStore.getState().encryption.setSession(null);
      return null;
    }
    return session;
  }

  // ---- 请求拦截器：签名 + 加密 ---------------------------------------

  const requestEncrypt: InterceptorConfig = {
    onFulfilled: async (request) => {
      const session = getSession();
      if (!session) {
        throw new Error("加密会话不可用，请求中止");
      }

      // FormData：文件上传场景
      if (request.data instanceof FormData) {
        return handleFormData(request, session, signatureSecret);
      }

      // JSON 请求
      const contentType = request.headers["content-type"] || "";
      if (!contentType.includes("application/json")) {
        throw new Error(`不支持加密的内容类型: ${contentType}`);
      }
      if (typeof request.data !== "object" || request.data === null) {
        throw new Error("请求体格式异常，无法加密");
      }
      if (isEncryptedPayload(request.data)) {
        throw new Error("请求体已加密，重复加密");
      }

      return handleJson(request, session, signatureSecret);
    },
  };

  // ---- 响应拦截器：解密 ---------------------------------------------

  const responseDecrypt: InterceptorConfig = {
    onFulfilled: async (response) => {
      if (response.headers["content-type"]?.includes("text/event-stream")) {
        return response;
      }

      if (!isEncryptedPayload(response.data)) return response;

      const session = getSession();
      if (!session) {
        throw new Error("加密会话不可用，无法解密响应");
      }

      const decryptedStr = await decryptPayload(
        response.data as EncryptedResult,
        session.aesKey,
      );
      return {
        ...response,
        data: JSON.parse(decryptedStr),
      };
    },
  };

  return { requestEncrypt, responseDecrypt };
}

// ==== 私有 ==========================================================

/** 处理 JSON 请求：签名 + 加密 */
async function handleJson(
  request: {
    data: unknown;
    headers: Record<string, string>;
    [key: string]: unknown;
  },
  session: EncryptionSession,
  signatureSecret: string,
): Promise<unknown> {
  const signedData = await signParams(
    request.data as Record<string, unknown>,
    signatureSecret,
  );
  const jsonStr = JSON.stringify(signedData);
  const encrypted = await encryptJson(jsonStr, session);

  return {
    ...request,
    data: encrypted,
    headers: {
      ...request.headers,
      "x-encrypt-enabled": "1",
      "x-encrypt-version": ENCRYPTION_VERSION,
      "x-signature-version": SIGNATURE_VERSION,
    },
  };
}

/** 处理 FormData 请求：加密 meta_json + 添加签名字段到 FormData */
async function handleFormData(
  request: {
    data: FormData;
    headers: Record<string, string>;
    [key: string]: unknown;
  },
  session: EncryptionSession,
  signatureSecret: string,
): Promise<unknown> {
  const formData = request.data as FormData;
  const metaJson = formData.get("meta_json") as string | null;
  const meta = metaJson ? JSON.parse(metaJson) : {};

  // 签名
  const timestamp = Date.now();
  const nonce = generateNonce();
  const signature = await computeSignature(
    meta,
    signatureSecret,
    timestamp,
    nonce,
  );

  // 加密 meta_json
  const encrypted = await encryptJson(JSON.stringify(meta), session);

  // 重新组装 FormData：替换 meta_json 为加密版本，添加签名
  const newFormData = new FormData();
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
      "x-encrypt-version": ENCRYPTION_VERSION,
      "x-signature-version": SIGNATURE_VERSION,
    },
  };
}

function isEncryptedPayload(data: unknown): data is EncryptedResult {
  return (
    typeof data === "object" &&
    data !== null &&
    typeof (data as EncryptedResult).encrypted === "string" &&
    typeof (data as EncryptedResult).nonce === "string" &&
    typeof (data as EncryptedResult).keyId === "string"
  );
}
