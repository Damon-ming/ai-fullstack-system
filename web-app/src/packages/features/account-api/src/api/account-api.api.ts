// web-app/src/packages/features/account-api/src/api/account-api.api.ts
/**
 * 账号模块对外 API —— 仅做 re-export，不包含实现。
 */

export { useAccount } from "@ming/feature-account";
export type { AccountProfile } from "@ming/feature-account";

// ---- Token 编排（来自 hook 层） ----
export { initDeviceToken, refreshDeviceToken } from "@ming/feature-account";
