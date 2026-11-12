// web-app/src/packages/features/account/src/api/account.api.ts
/**
 * 账号 API 层 —— 纯透传通道。
 *
 * 职责：
 *   - 网络请求（login / fetchProfile / updateProfile）：返回原始 DataApiResponse，
 *     不解包、不转换、不做业务判断
 *   - 存储原语 re-export：getSessionContext / setSessionContext /
 *     clearSessionContext / setDeviceId —— 直接透传 biz-common-storage，
 *     不附加任何逻辑
 *
 * 不做：
 *   - 业务编排（"有缓存就跳过"、"失败了怎么办"）→ hook/ 层
 *   - 存储 + 网络的原子组合 → hook/ 层
 *   - 任何条件判断或抛错 → hook/ 层
 */

import { dataApi } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import { createLogger } from "@ming/core-log";

import type {
  LoginRequest,
  DeviceTokenResponse,
  ProfileRequest,
  ProfileResponse,
} from "./types";

const log = createLogger("account/api");

// ---------------------------------------------------------------------------
// 存储原语 —— 直接 re-export，api 层不附加任何逻辑
// ---------------------------------------------------------------------------

export {
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
} from "@ming/biz-common-storage";

// ---------------------------------------------------------------------------
// 网络请求 —— 纯 HTTP 调用，返回原始 DataApiResponse
// ---------------------------------------------------------------------------

/** 登录（手机号未注册时自动注册）。 */
export async function login(
  body: LoginRequest,
): Promise<DataApiResponse<DeviceTokenResponse>> {
  log.debug("登录请求", { phone: body.phone.slice(0, 3) + "***" });
  return dataApi.post<DeviceTokenResponse>("/api/account/login/v1", body);
}

/** 获取当前用户昵称。 */
export async function fetchProfile(): Promise<
  DataApiResponse<ProfileResponse>
> {
  log.debug("获取用户资料");
  return dataApi.get<ProfileResponse>("/api/account/profile/get/v1");
}

/** 更新当前用户昵称。 */
export async function updateProfile(
  body: ProfileRequest,
): Promise<DataApiResponse<ProfileResponse>> {
  log.debug("更新用户资料", { name: body.name });
  return dataApi.post<ProfileResponse>("/api/account/profile/update/v1", body);
}
