// web-app/src/packages/features/account/src/hook/AccountHook.ts
/**
 * 账号 Hook 层 —— 业务编排 + 本地状态管理。
 *
 * 职责：
 *   - 用户资料状态（accountStore）
 *   - Token 生命周期编排（读缓存 → 调 API → 写缓存）
 *   - device_id 缓存（API 返回后写入 localStorage）
 *
 * API 层只负责 HTTP + 打印，不包含任何业务逻辑。
 */

import { useState } from "react";
import { createLogger } from "@ming/core-log";
import {
  getDeviceToken,
  setDeviceToken,
  clearDeviceToken,
  getDeviceId,
  setDeviceId,
} from "@ming/biz-common-util";
import { requestDeviceToken, SIMULATED_PHONE } from "../api";
import type { AccountProfile } from "../api/types";

const log = createLogger("account/hook");

// ---------------------------------------------------------------------------
// 用户资料（本地存储）
// ---------------------------------------------------------------------------

const PROFILE_KEY = "ming-ai-account";
const fallback: AccountProfile = {
  id: "murphy",
  name: "Murphy",
  avatarText: "M",
};

export const accountStore = {
  current(): AccountProfile {
    if (typeof window === "undefined") return fallback;
    try {
      return {
        ...fallback,
        ...JSON.parse(localStorage.getItem(PROFILE_KEY) || "{}"),
      };
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
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    return profile;
  },
};

// ---------------------------------------------------------------------------
// Token 编排（检查缓存 → 调 API → 写缓存）
// ---------------------------------------------------------------------------

/** 申请 token，已有则跳过。 */
export async function initDeviceToken(): Promise<string> {
  const existing = getDeviceToken();
  if (existing) return existing;

  const [err, resp] = await requestDeviceToken({ phone: SIMULATED_PHONE });

  if (err || !resp?.data?.token) {
    throw log.serverThrow(
      new Error(
        `Token 签发失败: ${err?.data?.error_msg || "CLIENT: 未知错误"}`,
      ),
    );
  }

  // 缓存 token + device_id 到 localStorage
  setDeviceToken(resp.data.token);
  if (resp.data.device_id) {
    setDeviceId(resp.data.device_id);
  }

  log.info("Token 已签发", {
    device_id: resp.data.device_id?.slice(0, 12) + "...",
  });
  return resp.data.token;
}

/** 重新签发 token（清除缓存后重新申请）。 */
export async function refreshDeviceToken(): Promise<string> {
  clearDeviceToken();
  return initDeviceToken();
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAccount() {
  const [profile, setProfile] = useState(() => accountStore.current());
  const update = (name: string) => {
    const next = accountStore.update(name);
    setProfile(next);
    return next;
  };
  return { profile, update };
}
