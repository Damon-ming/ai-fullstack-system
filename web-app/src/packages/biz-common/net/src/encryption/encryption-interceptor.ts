// web-app/src/packages/biz-common/net/src/encryption/encryption-interceptor.ts
/**
 * 加密 + 签名拦截器 — 纯加解密，不感知密钥交换。
 *
 * 密钥交换在 bootstrap 阶段由 features-encryption-api 完成，
 * 会话写入 localStorage，拦截器从 biz-common-util 读取。
 *
 * 支持两种请求类型：
 *   1. JSON: 整体签名 → 整体加密
 *   2. FormData (文件上传): 提取 meta_json → 签名 + 加密 meta → 重新组装 FormData
 *
 * 请求头（加密协议层，仅版本控制 + 加密开关）：
 *   X-Encrypt-Enabled: 1       → 服务端对响应也加密
 *   X-Encrypt-Version: v1      → 客户端加密协议版本
 *   X-Signature-Version: v1    → 客户端签名协议版本
 *
 * 签名数据（timestamp/nonce/signature）的传递方式：
 *   JSON 请求：放入 body，参与签名后整体加密（服务端从解密后的 body 读取）
 *   FormData 请求：作为独立 form 字段（timestamp、nonce、signature），
 *                  meta_json 加密为 meta_json_encrypted
 *
 * 加密 payload 内也携带 version 字段（防篡改，认证后验证）
 *
 * 响应流程：
 *   收到密文 → 解密 → 明文 JSON
 */

import type { InterceptorConfig } from "@ming/core-network";
import { createLogger } from "@ming/core-log";
import { generateNonce } from "@ming/core-encryption";
import { getEncryptionSession } from "@ming/biz-common-storage";
import { encryptJson, decryptPayload } from "./encryption-crypto";
import { computeSignature, signParams } from "./signature";
import type { EncryptedResult, EncryptionSession } from "./encryption-types";
import { ENCRYPTION_VERSION, SIGNATURE_VERSION } from "./encryption-types";

const log = createLogger("net/encryption");

// ---------------------------------------------------------------------------
// 工厂函数
// ---------------------------------------------------------------------------

export interface EncryptionInterceptorOptions {
  /**
   * 加密白名单 —— 命中这些前缀的请求跳过加密/解密。
   * 由调用方注入，拦截器本身不感知业务路径。
   */
  excludePaths?: string[];
}

export function createEncryptionInterceptors(
  options: EncryptionInterceptorOptions = {},
): {
  requestEncrypt: InterceptorConfig;
  responseDecrypt: InterceptorConfig;
} {
  const excludePaths = options.excludePaths ?? [];

  /** 检查 URL 是否命中排除前缀 */
  const isExcluded = (url: string | undefined): boolean => {
    if (!url || excludePaths.length === 0) return false;
    return excludePaths.some((prefix) => url.startsWith(prefix));
  };

  // ---- 请求拦截器：签名 + 加密 ---------------------------------------

  const requestEncrypt: InterceptorConfig = {
    onFulfilled: async (request) => {
      // 白名单路径：不加密，直接放行
      if (isExcluded(request.url)) {
        log.debug("加密白名单命中，跳过加密: %s", request.url);
        return request;
      }

      const session = await getEncryptionSession();
      if (!session) {
        log.error("加密会话不可用，请求中止");
        throw new Error("加密会话不可用，请求中止");
      }

      // FormData：文件上传场景
      if (request.data instanceof FormData) {
        return handleFormData(request, session);
      }

      // JSON 请求
      const contentType = request.headers["content-type"] || "";
      if (!contentType.includes("application/json")) {
        log.error("不支持加密的内容类型: %s", contentType);
        throw new Error(`不支持加密的内容类型: ${contentType}`);
      }
      if (typeof request.data !== "object" || request.data === null) {
        log.error("请求体格式异常，无法加密");
        throw new Error("请求体格式异常，无法加密");
      }
      if (isEncryptedPayload(request.data)) {
        log.error("请求体已加密，重复加密");
        throw new Error("请求体已加密，重复加密");
      }

      return handleJson(request, session);
    },
  };

  // ---- 响应拦截器：解密 ---------------------------------------------

  const responseDecrypt: InterceptorConfig = {
    onFulfilled: async (response) => {
      if (response.headers["content-type"]?.includes("text/event-stream")) {
        return response;
      }

      // 白名单路径：不尝试解密，直接放行
      if (isExcluded(response.config?.url)) {
        return response;
      }

      if (!isEncryptedPayload(response.data)) return response;

      const session = await getEncryptionSession();
      if (!session) {
        log.error("加密会话不可用，无法解密响应");
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
): Promise<unknown> {
  const signedData = await signParams(
    request.data as Record<string, unknown>,
    session.signatureKeyHex,
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
): Promise<unknown> {
  const formData = request.data as FormData;
  const metaJson = formData.get("meta_json") as string | null;
  const meta = metaJson ? JSON.parse(metaJson) : {};

  // 签名
  const timestamp = Date.now();
  const nonce = generateNonce();
  const signature = await computeSignature(
    meta,
    session.signatureKeyHex,
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
