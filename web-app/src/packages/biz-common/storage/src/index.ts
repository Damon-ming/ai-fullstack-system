// src/packages/biz-common/storage/src/index.ts

// 认证态（单个设备会话 token）
export {
  getStoredToken,
  setStoredToken,
  clearStoredToken,
} from "./auth-store";

// 加密会话（密钥交换后由 bootstrap 写入，加密拦截器读取）
export {
  setEncryptionSession,
  getEncryptionSession,
  clearEncryptionSession,
} from "./encryption-store";
export type { EncryptionSession } from "./encryption-store";
