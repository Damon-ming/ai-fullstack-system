// web-app/src/packages/features/account/src/hook/AccountHook.ts
/**
 * 账号 Hook 层 —— 业务编排 + 状态管理。
 *
 * 职责：
 *   - 用户资料状态（服务端为唯一数据源）
 *   - Token 生命周期编排：读缓存 → 判断 → 调 API → 写缓存
 *   - 通过 api/ 层调用网络和持久化，不直接依赖 biz-common-storage 实现
 *
 * 所有涉及存储读写的决策（何时读、何时写、读了之后怎么做）都在本层完成，
 * api/ 层只做原始透传。
 */

import { useEffect, useState } from "react";
import { createLogger } from "@ming/core-log";
import {
  fetchProfile,
  updateProfile,
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
  SIMULATED_PHONE,
  SIMULATED_PASSWORD,
} from "../api";
import { login as loginApi } from "../api/account.api";
import type { AccountProfile } from "../api/types";

const log = createLogger("account/hook");

// ---------------------------------------------------------------------------
// Token 编排 —— 业务决策层：何时读缓存、何时调 API、何时写缓存
// ---------------------------------------------------------------------------

/**
 * 登录（已有缓存则跳过，否则调 API 登录/自动注册）。
 * 编排：读缓存 → 有则返回 → 无则调 API → 写缓存 → 返回 token。
 */
export async function login(): Promise<string> {
  const existing = getSessionContext();
  if (existing?.token) return existing.token;

  const res = await loginApi({
    phone: SIMULATED_PHONE,
    password: SIMULATED_PASSWORD,
  });

  if (!res.data?.token) {
    throw new Error("登录失败: 服务端未返回有效 token");
  }

  if (res.data.device_id) {
    setDeviceId(res.data.device_id);
  }

  setSessionContext({
    token: res.data.token,
    sessionId: res.data.session_id,
  });

  log.info("登录完成", {
    device_id: res.data.device_id?.slice(0, 12) + "...",
    session_id: res.data.session_id?.slice(0, 8) + "...",
  });
  return res.data.token;
}

/** 重新登录（清除缓存后重新登录）。 */
export async function refreshDeviceToken(): Promise<string> {
  clearSessionContext();
  return login();
}

// ---------------------------------------------------------------------------
// 用户资料 Hook
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
