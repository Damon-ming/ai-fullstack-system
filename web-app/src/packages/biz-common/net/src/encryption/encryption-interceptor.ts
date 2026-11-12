// web-app/src/packages/biz-common/net/src/encryption/encryption-interceptor.ts
/**
 * 加密 + 签名拦截器 — 纯加解密，不感知密钥交换。
 *
 * 密钥交换在登录之后由 app 层触发（features-encryption-api），
 * 会话写入 localStorage，拦截器从 biz-common-storage 读取。
 *
 * 是否放行由服务端策略决定（release 强制加密、debug 由开关决定），
 * 客户端不做路径白名单：命中服务端白名单的请求本就无密文可发，
 * 这里「无会话即明文」的懒惰策略对所有端点天然成立。
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
 *   SSE 响应不走本拦截器（见 decryptSsePayload）
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

export function createEncryptionInterceptors(): {
  requestEncrypt: InterceptorConfig;
  responseDecrypt: InterceptorConfig;
} {
  // ---- 请求拦截器：签名 + 加密 ---------------------------------------

  const requestEncrypt: InterceptorConfig = {
    onFulfilled: async (request) => {
      const session = await getEncryptionSession();
      if (!session) {
        // 无加密会话 → 明文放行。
        // 登录 / 密钥交换本身必须走这条路（会话尚未建立）；
        // release 下其它请求会被服务端以 ENCRYPTION_REQUIRED 拒绝（fail-closed）。
        log.debug("无加密会话，跳过加密: %s", request.url);
        return request;
      }

      // FormData：文件上传场景
      if (request.data instanceof FormData) {
        return handleFormData(request, session);
      }

      // GET / HEAD 等无 body 的请求：无数据可加密，直接放行
      const method = (request.method ?? "GET").toUpperCase();
      if (method === "GET" || method === "HEAD") {
        log.debug("GET/HEAD 请求跳过加密: %s", request.url);
        return request;
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

// ---------------------------------------------------------------------------
// SSE 事件解密
// ---------------------------------------------------------------------------

/**
 * 解密 SSE 事件的 data 字段。
 *
 * 服务端对每个事件的 data 单独加密（event / id / retry 保持明文以便路由），
 * 因此这里只负责「data → 明文对象」，协议字段由 SSE 解析器处理。
 *
 * 明文链路（debug 未开启加密 / 命中服务端白名单）时 data 本身就是业务 JSON，
 * 解析后原样返回；非 JSON 字符串（心跳等）也原样返回。
 */
export async function decryptSsePayload(raw: string): Promise<unknown> {
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    return raw;
  }
  if (!isEncryptedPayload(payload)) return payload;

  const session = await getEncryptionSession();
  if (!session) {
    log.error("SSE 解密失败：加密会话不可用");
    throw new Error("SSE 解密失败：加密会话不可用");
  }
  const decryptedStr = await decryptPayload(payload, session.aesKey);
  return JSON.parse(decryptedStr);
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
