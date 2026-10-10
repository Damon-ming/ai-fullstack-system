// web-app/src/packages/features/account/src/api/account.api.ts
import { netClient } from "@ming/biz-common-net-api";
import type { BizResult } from "@ming/biz-common-net-api";
import { createLogger } from "@ming/core-log";
import type {
  DeviceTokenRequest,
  DeviceTokenResponse,
  AccountProfile,
} from "./types";

const log = createLogger("account/api");

// ---------------------------------------------------------------------------
// 设备唯一 ID（TODO: 后期替换为手机号）
// ---------------------------------------------------------------------------

const DEVICE_ID_KEY = "__device_id__";

/**
 * 获取或创建持久化的设备唯一 ID。
 * 存入 localStorage，同一浏览器生命周期内保持不变。
 * TODO: 后期替换为手机号，由用户输入 + 服务端验证
 */
function getOrCreateDeviceId(): string {
  if (typeof window === "undefined") return "server-side";
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    // 32 字节随机 hex，仅作设备标识，不参与 token 生成逻辑
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    id = Array.from(bytes)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

// ---------------------------------------------------------------------------
// 账号资料（本地存储）
// ---------------------------------------------------------------------------

const key = "ming-ai-account";
const fallback: AccountProfile = {
  id: "murphy",
  name: "Murphy",
  avatarText: "M",
};

export const accountStore = {
  current(): AccountProfile {
    if (typeof window === "undefined") return fallback;
    try {
      return { ...fallback, ...JSON.parse(localStorage.getItem(key) || "{}") };
    } catch {
      return fallback;
    }
  },
  update(name: string) {
    const normalized = name.trim() || fallback.name;
    const profile = {
      ...fallback,
      ...this.current(),
      name: normalized,
      avatarText: normalized.slice(0, 1).toUpperCase(),
    };
    localStorage.setItem(key, JSON.stringify(profile));
    return profile;
  },
};

// ---------------------------------------------------------------------------
// 设备 Token（服务端签发）
// ---------------------------------------------------------------------------

const TOKEN_KEY = "__device_token__";

/** 同步读取当前缓存的设备 token（供拦截器使用）。 */
export function getDeviceToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/** 从服务端申请设备 token，已有则跳过。 */
export async function initDeviceToken(): Promise<string> {
  const existing = getDeviceToken();
  if (existing) return existing;

  const deviceId = getOrCreateDeviceId();
  const [err, resp] = await requestDeviceToken({ device_id: deviceId });

  if (err || !resp?.data?.token) {
    throw new Error(
      `设备 Token 签发失败: ${err?.data?.error_msg || "未知错误"}`,
    );
  }

  localStorage.setItem(TOKEN_KEY, resp.data.token);
  return resp.data.token;
}

/** 重新从服务端签发 token。 */
export async function refreshDeviceToken(): Promise<string> {
  localStorage.removeItem(TOKEN_KEY);
  return initDeviceToken();
}

/**
 * 原始 HTTP 调用 —— 申请设备 token。
 * @internal
 */
export async function requestDeviceToken(
  body: DeviceTokenRequest,
): Promise<BizResult<DeviceTokenResponse>> {
  log.debug("申请设备 token");
  return netClient.post<DeviceTokenResponse>("/api/account/token/v1", body);
}
