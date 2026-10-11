// web-app/src/packages/biz-common/net/src/encryption/signature.ts
/**
 * 请求签名 — 业务层
 *
 * 本模块定义项目特定的签名协议：
 *   1. 取请求参数（排除 signature/timestamp/nonce），按 key 升序排序
 *   2. 拼接成 key1=v1&key2=v2 格式
 *   3. 加上 timestamp + nonce
 *   4. HMAC-SHA256(secret, 拼接串) → hex
 *
 * 纯 HMAC 原语在 @ming/core-encryption，这里只负责协议组装。
 */

import { hmacSha256 } from "@ming/core-encryption";

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

/** 不参与签名的参数 key */
const SIGN_EXCLUDE_KEYS = new Set(["signature", "timestamp", "nonce"]);

// ---------------------------------------------------------------------------
// 公开
// ---------------------------------------------------------------------------

/**
 * 计算请求签名（协议层封装）
 *
 * @param params — 请求参数对象
 * @param secret — 签名密钥
 * @param timestamp — 时间戳（毫秒）
 * @param nonce — 随机字符串
 * @returns hex 格式的签名字符串
 */
export async function computeSignature(
  params: Record<string, unknown>,
  secret: string,
  timestamp: number,
  nonce: string,
): Promise<string> {
  // 1. 排序并拼接业务参数（排除签名字段自身）
  const sortedKeys = Object.keys(params)
    .filter((k) => !SIGN_EXCLUDE_KEYS.has(k))
    .sort((a, b) => a.localeCompare(b));

  const parts: string[] = [];
  for (const key of sortedKeys) {
    const val = params[key];
    // 跳过 undefined / null / 文件对象（文件不参与签名）
    if (val === undefined || val === null || val instanceof File) continue;
    parts.push(`${key}=${stringifyValue(val)}`);
  }
  const paramStr = parts.join("&");

  // 2. 加上 timestamp + nonce
  const signContent = `${paramStr}|ts=${timestamp}|nonce=${nonce}`;

  // 3. HMAC-SHA256
  return hmacSha256(secret, signContent);
}

// ---------------------------------------------------------------------------
// 私有
// ---------------------------------------------------------------------------

/** 将参数值转为可签名的字符串 */
function stringifyValue(val: unknown): string {
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}
