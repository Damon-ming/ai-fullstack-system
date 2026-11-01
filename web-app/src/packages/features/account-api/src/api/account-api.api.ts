// account-api/src/api/account-api.api.ts
/**
 * 账号模块对外 API —— 仅做 re-export，不包含实现。
 */

export {
  useAccount,
  useLoginPageHook,
  login,
  refreshDeviceToken,
  validatePhone,
  validatePassword,
  validateLoginForm,
} from "@ming/feature-account";
export { LoginPage } from "@ming/feature-account";
export type {
  AccountProfile,
  ValidationResult,
  LoginStatus,
} from "@ming/feature-account";
