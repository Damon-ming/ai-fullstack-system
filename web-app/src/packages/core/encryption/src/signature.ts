// web-app/src/packages/core/encryption/src/signature.ts
/**
 * HMAC-SHA256 纯原语
 *
 * 只提供：
 *   - 随机 nonce 生成
 *   - 对任意消息字符串计算 HMAC-SHA256
 *
 * 签名协议（参数排序、拼接格式、排除规则、timestamp/nonce 组装）属于业务层，
 * 不在此模块中。
 */

// ---------------------------------------------------------------------------
// Nonce
// ---------------------------------------------------------------------------

/** 生成随机 nonce（hex 字符串） */
export function generateNonce(length = 16): string {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  let hex = "";
  for (const b of bytes) hex += b.toString(16).padStart(2, "0");
  return hex;
}

// ---------------------------------------------------------------------------
// HMAC-SHA256
// ---------------------------------------------------------------------------

/**
 * 计算 HMAC-SHA256
 *
 * @param secret  密钥字符串
 * @param message 待签名的消息字符串
 * @returns hex 格式的签名字符串
 */
export async function hmacSha256(
  secret: string,
  message: string,
): Promise<string> {
  const keyData = new TextEncoder().encode(secret);
  const msgData = new TextEncoder().encode(message);

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const sigBuffer = await crypto.subtle.sign("HMAC", cryptoKey, msgData);

  const bytes = new Uint8Array(sigBuffer);
  let hex = "";
  for (const b of bytes) hex += b.toString(16).padStart(2, "0");
  return hex;
}
