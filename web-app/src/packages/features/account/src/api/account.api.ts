// web-app/src/packages/features/account/src/api/account.api.ts
/**
 * 账号 API 层 —— 负责：网络请求、持久化（LocalStorage）、打印日志、透传结果。
 *
 * 包含：
 *   - 纯 HTTP 调用（login / fetchProfile / updateProfile）
 *   - 持久化封装（session context / device_id 读写）
 *   - 编排函数（initDeviceToken / refreshDeviceToken：网络 + 持久化原子组合）
 *
 * 不包含：
 *   - React 状态管理（由 hook 层持有）
 *   - UI 逻辑
 */

import { dataApi } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import { createLogger } from "@ming/core-log";
import {
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
} from "@ming/biz-common-storage";
import type {
  DeviceTokenRequest,
  DeviceTokenResponse,
  ProfileRequest,
  ProfileResponse,
} from "./types";

const log = createLogger("account/api");
export const SIMULATED_PHONE = "+8613800138000";

// ---------------------------------------------------------------------------
// 持久化封装 —— 封装 biz-common-storage，hook 层不直接依赖存储实现
// ---------------------------------------------------------------------------

export {
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
} from "@ming/biz-common-storage";

// ---------------------------------------------------------------------------
// 登录 —— 纯 HTTP 调用，返回 DataApiResponse 透传给 hook 层
// ---------------------------------------------------------------------------

/**
 * 登录（申请设备 Token）。
 * 服务端根据手机号返回 token + device_id + session_id。
 */
export async function login(
  body: DeviceTokenRequest,
): Promise<DataApiResponse<DeviceTokenResponse>> {
  log.debug("登录请求", { phone: body.phone.slice(0, 3) + "***" });
  return dataApi.post<DeviceTokenResponse>("/api/account/login/v1", body);
}

// ---------------------------------------------------------------------------
// 用户资料 —— 纯 HTTP 调用
// ---------------------------------------------------------------------------

/** 获取当前用户昵称。 */
export async function fetchProfile(): Promise<
  DataApiResponse<ProfileResponse>
> {
  log.debug("获取用户资料");
  return dataApi.get<ProfileResponse>("/api/account/profile/v1");
}

/** 更新当前用户昵称。 */
export async function updateProfile(
  body: ProfileRequest,
): Promise<DataApiResponse<ProfileResponse>> {
  log.debug("更新用户资料", { name: body.name });
  return dataApi.post<ProfileResponse>("/api/account/profile/v1", body);
}

// ---------------------------------------------------------------------------
// 编排函数 —— 网络 + 持久化原子组合（由 api 层封装，hook 层只调结果）
// ---------------------------------------------------------------------------

/**
 * 登录申请 token，已有则跳过。
 * 封装了"读缓存 → 调 API → 写缓存"的完整编排。
 */
export async function initDeviceToken(): Promise<string> {
  const existing = getSessionContext();
  if (existing?.token) return existing.token;

  const res = await login({ phone: SIMULATED_PHONE });

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

  log.info("Token 已签发", {
    device_id: res.data.device_id?.slice(0, 12) + "...",
    session_id: res.data.session_id?.slice(0, 8) + "...",
  });
  return res.data.token;
}

/** 重新登录（清除缓存后重新申请）。 */
export async function refreshDeviceToken(): Promise<string> {
  clearSessionContext();
  return initDeviceToken();
}
