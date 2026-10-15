// web-app/src/packages/features/account/src/hook/AccountHook.ts
/**
 * 账号 Hook 层 — 业务编排 + 服务端状态管理。
 *
 * 职责：
 *   - 用户资料状态（服务端为唯一数据源）
 *   - 会话上下文编排（token + device_id + session_id 原子读写）
 *
 * API 层只负责 HTTP + 打印，不包含任何业务逻辑。
 */

import { useEffect, useState } from "react";
import { createLogger } from "@ming/core-log";
import {
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
} from "@ming/biz-common-storage";
import { login, fetchProfile, updateProfile, SIMULATED_PHONE } from "../api";
import type { AccountProfile } from "../api/types";

const log = createLogger("account/hook");

// ---------------------------------------------------------------------------
// 会话上下文编排（读缓存 → 调 API → 原子写缓存）
// ---------------------------------------------------------------------------

/** 登录申请 token，已有则跳过。 */
export async function initDeviceToken(): Promise<string> {
  const existing = getSessionContext();
  if (existing?.token) return existing.token;

  try {
    const res = await login({ phone: SIMULATED_PHONE });

    if (!res.data?.token) {
      throw new Error("登录失败: 服务端未返回有效 token");
    }

    // 设备身份独立存储（设备生命周期，不随 token 清除）
    if (res.data.device_id) {
      setDeviceId(res.data.device_id);
    }

    // 会话上下文原子写入：token + session_id 同时生效
    setSessionContext({
      token: res.data.token,
      sessionId: res.data.session_id,
    });

    log.info("Token 已签发", {
      device_id: res.data.device_id?.slice(0, 12) + "...",
      session_id: res.data.session_id?.slice(0, 8) + "...",
    });
    return res.data.token;
  } catch (e) {
    const msg = e instanceof Error ? e.message : "登录请求失败";
    throw new Error(msg);
  }
}

/** 重新登录（清除缓存后重新申请）。 */
export async function refreshDeviceToken(): Promise<string> {
  clearSessionContext();
  return initDeviceToken();
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAccount() {
  const [profile, setProfile] = useState<AccountProfile>({
    id: "",
    name: "",
    avatarText: "",
  });

  // 挂载时从服务端拉取昵称
  useEffect(() => {
    fetchProfile()
      .then((res) => {
        const name = res.data?.name;
        if (name) {
          setProfile({
            id: name.toLowerCase(),
            name,
            avatarText: name.slice(0, 1).toUpperCase(),
          });
        }
      })
      .catch(() => {
        // 服务端不可用时保持空状态
      });
  }, []);

  const update = async (name: string) => {
    const normalized = name.trim();
    if (!normalized) return profile;
    const res = await updateProfile({ name: normalized });
    const savedName = res.data?.name || normalized;
    const next: AccountProfile = {
      id: savedName.toLowerCase(),
      name: savedName,
      avatarText: savedName.slice(0, 1).toUpperCase(),
    };
    setProfile(next);
    return next;
  };

  return { profile, update };
}
