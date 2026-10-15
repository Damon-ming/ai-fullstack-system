// web-app/src/packages/features/account/src/api/account.api.ts
/**
 * 账号 API 层 —— 仅负责：网络请求、打印日志、透传结果。
 *
 * 不包含：
 *   - localStorage 读写（由 hook 层处理）
 *   - token / device_id 缓存逻辑（由 hook 层编排）
 *   - 业务状态管理（accountStore 等，由 hook 层持有）
 */

import { dataApi } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import { createLogger } from "@ming/core-log";
import type {
  DeviceTokenRequest,
  DeviceTokenResponse,
  ProfileRequest,
  ProfileResponse,
} from "./types";

const log = createLogger("account/api");
export const SIMULATED_PHONE = "+8613800138000";

// ---------------------------------------------------------------------------
// 登录 —— 纯 HTTP 调用，返回 DataApiResponse 透传给 hook 层
// ---------------------------------------------------------------------------

/**
 * 登录（申请设备 Token）。
 * 服务端根据手机号返回 token + device_id + session_id。
 * @internal 由 hook 层 initDeviceToken / refreshDeviceToken 调用
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

/**
 * 获取当前用户昵称。
 */
export async function fetchProfile(): Promise<DataApiResponse<ProfileResponse>> {
  log.debug("获取用户资料");
  return dataApi.get<ProfileResponse>("/api/account/profile/v1");
}

/**
 * 更新当前用户昵称。
 */
export async function updateProfile(
  body: ProfileRequest,
): Promise<DataApiResponse<ProfileResponse>> {
  log.debug("更新用户资料", { name: body.name });
  return dataApi.post<ProfileResponse>("/api/account/profile/v1", body);
}
