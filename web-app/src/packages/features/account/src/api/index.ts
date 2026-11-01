// web-app/src/packages/features/account/src/api/index.ts
// API 层导出 —— HTTP 调用 + 持久化封装 + 编排函数
export {
  login,
  fetchProfile,
  updateProfile,
  SIMULATED_PHONE,
  initDeviceToken,
  refreshDeviceToken,
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
} from "./account.api";
export type {
  AccountProfile,
  DeviceTokenRequest,
  DeviceTokenResponse,
  ProfileRequest,
  ProfileResponse,
} from "./types";
