// web-app/src/packages/core/encryption/src/signature.ts
/**
 * 请求签名工具 — HMAC-SHA256
 *
 * 签名方案：
 *   1. 取请求参数（排除 signature 自身），按 key 升序排序
 *   2. 拼接成 key1=v1&key2=v2 格式
 *   3. 加上 timestamp + nonce
 *   4. HMAC-SHA256(secret, 拼接串) → hex
 */

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const SIGN_EXCLUDE_KEYS = new Set(["signature", "timestamp", "nonce"]);

// ---------------------------------------------------------------------------
// 工具
/** 生成随机 nonce */
export function generateNonce(length = 16): string {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  let hex = "";
  for (const b of bytes) hex += b.toString(16).padStart(2, "0");
  return hex;
}

/**
 * 计算 HMAC-SHA256 签名
 *
 * @param params  请求参数对象（不含 signature 字段）
 * @param secret  签名密钥（与服务端共享）
 * @param timestamp  当前时间戳（毫秒）
 * @param nonce  随机字符串
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
    .sort();

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
  const keyData = new TextEncoder().encode(secret);
  const msgData = new TextEncoder().encode(signContent);

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const sigBuffer = await crypto.subtle.sign("HMAC", cryptoKey, msgData);

  // 4. 转 hex
  const bytes = new Uint8Array(sigBuffer);
  let hex = "";
  for (const b of bytes) hex += b.toString(16).padStart(2, "0");
  return hex;
}

// ---------------------------------------------------------------------------
// 私有
/** 将参数值转为可签名的字符串 */
function stringifyValue(val: unknown): string {
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}
