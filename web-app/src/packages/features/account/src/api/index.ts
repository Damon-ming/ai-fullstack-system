// account/src/api/index.ts
// API 层导出 —— 纯透传：存储原语 + 网络请求
export {
  login,
  logout,
  fetchProfile,
  updateProfile,
  getStoredToken,
  setStoredToken,
  clearStoredToken,
  clearEncryptionSession,
} from "./account.api";
export type {
  AccountProfile,
  LoginRequest,
  LoginResponse,
  UpdateProfileRequest,
  ProfileResponse,
  UpdateProfileResponse,
} from "./types";
