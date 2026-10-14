// web-app/src/packages/features/account/src/hook/AccountHook.ts
/**
 * 账号 Hook 层 — 业务编排 + 本地状态管理。
 *
 * 职责：
 *   - 用户资料状态（accountStore）
 *   - 会话上下文编排（token + device_id + session_id 原子读写）
 *
 * API 层只负责 HTTP + 打印，不包含任何业务逻辑。
 */

import { useState } from "react";
import { createLogger } from "@ming/core-log";
import {
  getSessionContext,
  setSessionContext,
  clearSessionContext,
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
// 会话上下文编排（读缓存 → 调 API → 原子写缓存）
// ---------------------------------------------------------------------------

/** 申请 token，已有则跳过。 */
export async function initDeviceToken(): Promise<string> {
  const existing = getSessionContext();
  if (existing?.token) return existing.token;

  const [err, resp] = await requestDeviceToken({ phone: SIMULATED_PHONE });

  if (err || !resp?.data?.token) {
    // logging-interceptor 已记录完整 HTTP 错误（URL + 状态码 + 响应体），此处不再重复打印
    // clientData.message 是统一错误信息字段（服务端错误来自 error_msg，客户端错误来自 axios/拦截器）
    throw new Error(
      `Token 签发失败: ${err?.clientData?.message || "未知错误"}`,
    );
  }

  // 设备身份独立存储（设备生命周期，不随 token 清除）
  if (resp.data.device_id) {
    setDeviceId(resp.data.device_id);
  }

  // 会话上下文原子写入：token + session_id 同时生效
  setSessionContext({
    token: resp.data.token,
    sessionId: resp.data.session_id,
  });

  log.info("Token 已签发", {
    device_id: resp.data.device_id?.slice(0, 12) + "...",
    session_id: resp.data.session_id?.slice(0, 8) + "...",
  });
  return resp.data.token;
}

/** 重新签发 token（清除缓存后重新申请）。 */
export async function refreshDeviceToken(): Promise<string> {
  clearSessionContext();
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
