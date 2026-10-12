// web-app/src/packages/features/account/src/api/account.api.ts
/**
 * 账号 API 层 —— 仅负责：打印日志、装饰请求、透传结果。
 *
 * 不包含：
 *   - localStorage 读写（由 hook 层处理）
 *   - token / device_id 缓存逻辑（由 hook 层编排）
 *   - 业务状态管理（accountStore 等，由 hook 层持有）
 */

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
// 模拟手机号（TODO: 后期替换为用户真实输入）
// ---------------------------------------------------------------------------

export const SIMULATED_PHONE = "+8613800138000";

// ---------------------------------------------------------------------------
// Token —— 纯 HTTP 调用
// ---------------------------------------------------------------------------

/**
 * 申请设备 Token（原始 HTTP 调用）。
 * 服务端根据手机号返回 token + device_id。
 * @internal 由 hook 层 initDeviceToken / refreshDeviceToken 调用
 */
export async function requestDeviceToken(
  body: DeviceTokenRequest,
): Promise<BizResult<DeviceTokenResponse>> {
  log.debug("申请 token", { phone: body.phone.slice(0, 3) + "***" });
  return netClient.post<DeviceTokenResponse>("/api/account/token/v1", body);
}

// ---------------------------------------------------------------------------
// 用户资料（TODO: 后续抽取为独立资料接口时再扩展）
// ---------------------------------------------------------------------------

export interface AccountProfileResponse {
  data: AccountProfile;
}
