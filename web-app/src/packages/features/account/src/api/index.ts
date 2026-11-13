// account/src/api/index.ts
// API 层导出 —— 纯透传：存储原语 + 网络请求
export {
  login,
  fetchProfile,
  updateProfile,
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
  clearEncryptionSession,
} from "./account.api";
export type {
  AccountProfile,
  LoginRequest,
  DeviceTokenResponse,
  ProfileRequest,
  ProfileResponse,
} from "./types";
