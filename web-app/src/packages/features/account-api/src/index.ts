// account-api/src/index.ts
export {
  useAccount,
  useAccountDialogHook,
  useLoginPageHook,
  login,
  reloginWithPassword,
  createAuthInterceptors,
  validatePhone,
  validatePassword,
  validateLoginForm,
  LoginPage,
  AccountDialog,
} from "./api/account-api.api";
export type {
  AccountProfile,
  ValidationResult,
  LoginStatus,
} from "./api/account-api.api";
