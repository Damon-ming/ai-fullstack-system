// web-app/src/packages/features/account/src/api/index.ts
// API 层导出 —— 纯透传：存储原语 + 网络请求
export {
  fetchProfile,
  updateProfile,
  SIMULATED_PHONE,
  SIMULATED_PASSWORD,
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
} from "./account.api";
export type {
  AccountProfile,
  LoginRequest,
  DeviceTokenResponse,
  ProfileRequest,
  ProfileResponse,
} from "./types";
