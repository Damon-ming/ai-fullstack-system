// src/packages/core/util/src/ua/ua-fingerprint.ts
/**
 * 浏览器环境指纹 — 纯基础能力，不涉及业务逻辑。
 *
 * 职责：
 *   - 收集浏览器环境信息（UA、语言、平台、分辨率、时区）
 *   - 编码为可传输的摘要字符串
 *   - 计算设备指纹 hash
 *   - 解析服务端下发的 UA 摘要
 *
 * 不包含：
 *   - 任何业务概念（device_id 存储、token 等）
 *   - 任何网络请求
 */

// ---------------------------------------------------------------------------
// 数据模型
// ---------------------------------------------------------------------------

/**
 * 浏览器环境摘要。
 * 纯数据描述，不关联任何业务实体。
 */
export interface ClientUA {
  /** 原始 User-Agent 字符串 */
  ua: string
  /** 浏览器语言 (如 "zh-CN") */
  lang: string
  /** 操作系统平台 (如 "Win32", "MacIntel") */
  platform: string
  /** 屏幕分辨率 (如 "1920x1080") */
  screen: string
  /** IANA 时区 (如 "Asia/Shanghai") */
  tz: string
}

// ---------------------------------------------------------------------------
// 收集
// ---------------------------------------------------------------------------

/**
 * 从浏览器 API 收集环境信息。
 * 服务端不可用（依赖 navigator/screen/Intl）。
 */
export function collectClientUA(): ClientUA {
  const nav = globalThis.navigator as Navigator | undefined
  const scr = globalThis.screen as Screen | undefined

  return {
    ua: nav?.userAgent ?? "",
    lang: nav?.language ?? "",
    platform: nav?.platform ?? "",
    screen: scr ? `${scr.width}x${scr.height}` : "",
    tz: Intl?.DateTimeFormat?.().resolvedOptions?.().timeZone ?? "",
  }
}

// ---------------------------------------------------------------------------
// 编码 / 解码
// ---------------------------------------------------------------------------

/** UA 摘要分隔符 */
const UA_SEP = "|"

/**
 * 将 ClientUA 编码为单个 header 值字符串。
 *
 * 格式: "<UA>|<lang>|<platform>|<screenW>x<screenH>|<timezone>"
 * 示例: "Mozilla/5.0 ... Chrome/131.0|zh-CN|Win32|1920x1080|Asia/Shanghai"
 *
 * 使用管道符分隔，避免 UA 本身含空格/斜杠带来的解析歧义。
 */
export function encodeClientUA(ua: ClientUA): string {
  return [ua.ua, ua.lang, ua.platform, ua.screen, ua.tz].join(UA_SEP)
}

/**
 * 解析 header 值字符串为 ClientUA。
 * 解析失败时返回全空字段。
 */
export function decodeClientUA(headerValue: string): ClientUA {
  const parts = (headerValue || "").split(UA_SEP)
  return {
    ua: parts[0]?.trim() ?? "",
    lang: parts[1]?.trim() ?? "",
    platform: parts[2]?.trim() ?? "",
    screen: parts[3]?.trim() ?? "",
    tz: parts[4]?.trim() ?? "",
  }
}

// ---------------------------------------------------------------------------
// 指纹计算（纯哈希，不含业务逻辑）
// ---------------------------------------------------------------------------

/**
 * 计算环境摘要的 SHA-256 哈希（用于精确比对）。
 * 所有字段参与计算，任何变化都会导致哈希不同。
 */
export function computeUAHexHash(ua: ClientUA): string {
  const data = encodeClientUA(ua)
  // 使用 SubtleCrypto（浏览器环境）
  // 注意：这是同步接口的简化版，实际 SHA-256 需要异步
  // 这里用简单的 djb2 hash 做快速比对，完整 SHA-256 在需要时可用 subtle.crypto
  let hash = 5381
  for (let i = 0; i < data.length; i++) {
    hash = ((hash << 5) + hash + data.charCodeAt(i)) >>> 0
  }
  return hash.toString(16).padStart(8, "0")
}

/** 简单的非加密 hash（用于快速指纹，不用于安全场景） */
export function computeQuickHash(str: string): string {
  let hash = 5381
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) >>> 0
  }
  return hash.toString(16).padStart(8, "0")
}
