// web-app/src/packages/features/account/src/hook/AccountHook.ts
/**
 * 账号 Hook 层 —— 业务编排 + 服务端状态管理。
 *
 * 职责：
 *   - 用户资料状态（服务端为唯一数据源）
 *   - 通过 api 层调用网络和持久化，不直接依赖 biz-common-storage
 *
 * API 层负责 HTTP + 持久化 + 编排函数（initDeviceToken / refreshDeviceToken）。
 */

import { useEffect, useState } from "react";
import { createLogger } from "@ming/core-log";
import { fetchProfile, updateProfile } from "../api";
import type { AccountProfile } from "../api/types";

const log = createLogger("account/hook");

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
