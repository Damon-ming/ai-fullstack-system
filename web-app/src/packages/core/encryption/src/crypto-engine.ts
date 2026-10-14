// web-app/src/packages/core/encryption/src/crypto-engine.ts
/**
 * WebCrypto 底层加密原语 — 纯算法，零业务逻辑。
 *
 * - AES-GCM 加解密（浏览器原生 SubtleCrypto）
 * - RSA-OAEP 加密（仅用于加密 AES 密钥发给服务端）
 *
 * 不含 JSON 序列化、base64 编码、keyId 等协议/业务概念。
 * 可直接移植到任何需要 AES-GCM / RSA-OAEP 的项目。
 *
 * 注意：TypeScript 5.7+ 的 DOM lib 对 BufferSource 做了严格区分，
 * Uint8Array<ArrayBufferLike> 不再自动赋值给 BufferSource，
 * 需要通过 buffer 切片确保类型为 ArrayBuffer 后端。
 */

// ---------------------------------------------------------------------------
// 内部工具：确保 Uint8Array 基于 ArrayBuffer（兼容 TS 5.7 严格 BufferSource）
// ---------------------------------------------------------------------------

function toBufferSource(data: Uint8Array): ArrayBuffer {
  return data.buffer.slice(
    data.byteOffset,
    data.byteOffset + data.byteLength,
  ) as ArrayBuffer;
}

// ---------------------------------------------------------------------------
// AES-GCM 操作
// ---------------------------------------------------------------------------

/**
 * 生成 AES-256 原始密钥字节，并导入为 WebCrypto CryptoKey。
 * 返回 { rawKeyBytes, cryptoKey } —— rawKeyBytes 用于 RSA 加密传输。
 */
export async function generateAesKey(): Promise<{
  rawKeyBytes: Uint8Array;
  cryptoKey: CryptoKey;
}> {
  const cryptoKey = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true, // extractable — 我们需要导出原始字节给 RSA 加密
    ["encrypt", "decrypt"],
  );
  const rawKeyBuffer = await crypto.subtle.exportKey("raw", cryptoKey);
  return {
    rawKeyBytes: new Uint8Array(rawKeyBuffer),
    cryptoKey,
  };
}

/**
 * 从原始 AES 密钥字节导入 CryptoKey。
 */
export async function importAesKey(
  rawKeyBytes: Uint8Array,
): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    toBufferSource(rawKeyBytes),
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

/**
 * AES-GCM 加密。
 * 返回 { nonce, ciphertext }（ciphertext 已含 16 字节认证标签）。
 */
export async function aesEncrypt(
  plaintext: Uint8Array,
  cryptoKey: CryptoKey,
  aad?: Uint8Array,
): Promise<{ nonce: Uint8Array; ciphertext: Uint8Array }> {
  const nonce = crypto.getRandomValues(new Uint8Array(12)); // GCM 推荐 96 bit
  const algo: AesGcmParams = { name: "AES-GCM", iv: toBufferSource(nonce) };
  if (aad) algo.additionalData = toBufferSource(aad);

  const ctBuffer = await crypto.subtle.encrypt(
    algo,
    cryptoKey,
    toBufferSource(plaintext),
  );
  return {
    nonce,
    ciphertext: new Uint8Array(ctBuffer),
  };
}

/**
 * AES-GCM 解密。
 * 认证失败会 reject。
 */
export async function aesDecrypt(
  nonce: Uint8Array,
  ciphertext: Uint8Array,
  cryptoKey: CryptoKey,
  aad?: Uint8Array,
): Promise<Uint8Array> {
  const algo: AesGcmParams = { name: "AES-GCM", iv: toBufferSource(nonce) };
  if (aad) algo.additionalData = toBufferSource(aad);

  const ptBuffer = await crypto.subtle.decrypt(
    algo,
    cryptoKey,
    toBufferSource(ciphertext),
  );
  return new Uint8Array(ptBuffer);
}

// ---------------------------------------------------------------------------
// HKDF 密钥派生
// ---------------------------------------------------------------------------

/**
 * 使用 HKDF-SHA256 从主密钥派生出指定长度的原始密钥材料。
 *
 * 纯算法原语，不含业务语义。可用于派生签名密钥、封装密钥等任意用途。
 * context 由调用方传入（业务层协议常量），core/encryption 不包含该常量。
 *
 * 参数：
 *   masterKeyBytes: 主密钥原始字节（如 AES-256 密钥）
 *   context:        HKDF info 参数（标识密钥用途的协议常量）
 *   lengthBits:     派生输出长度（位），默认 256
 *
 * 返回：派生出的原始密钥字节
 */
export async function deriveKeyMaterial(
  masterKeyBytes: Uint8Array,
  context: string,
  lengthBits: number = 256,
): Promise<Uint8Array> {
  const masterCryptoKey = await crypto.subtle.importKey(
    "raw",
    toBufferSource(masterKeyBytes),
    { name: "HKDF" },
    false,
    ["deriveKey", "deriveBits"],
  );

  const bits = await crypto.subtle.deriveBits(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: new Uint8Array(0), // 无 salt
      info: new TextEncoder().encode(context),
    },
    masterCryptoKey,
    lengthBits,
  );

  return new Uint8Array(bits);
}

// ---------------------------------------------------------------------------
// RSA-OAEP 操作（仅用于加密 AES 密钥）
// ---------------------------------------------------------------------------

/**
 * 导入 PEM 格式 RSA 公钥 → CryptoKey。
 */
export async function importRsaPublicKey(pem: string): Promise<CryptoKey> {
  const pemBody = pem
    .replace(/-----BEGIN PUBLIC KEY-----/, "")
    .replace(/-----END PUBLIC KEY-----/, "")
    .replace(/\s/g, "");
  const binaryDer = _base64ToArrayBuffer(pemBody);

  return crypto.subtle.importKey(
    "spki",
    binaryDer,
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  );
}

/**
 * 用 RSA-OAEP 公钥加密数据（客户端 → 服务端：加密 AES 密钥）。
 */
export async function rsaEncrypt(
  data: Uint8Array,
  publicKey: CryptoKey,
): Promise<Uint8Array> {
  const ctBuffer = await crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    publicKey,
    toBufferSource(data),
  );
  return new Uint8Array(ctBuffer);
}

// ---------------------------------------------------------------------------
// Base64 工具
// ---------------------------------------------------------------------------

function _base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

/** Uint8Array → base64 字符串 */
export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/** Uint8Array → hex 字符串 */
export function bytesToHex(bytes: Uint8Array): string {
  let hex = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    hex += bytes[i].toString(16).padStart(2, "0");
  }
  return hex;
}

/** hex 字符串 → Uint8Array */
export function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}
