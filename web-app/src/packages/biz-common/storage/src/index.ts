// src/packages/biz-common/storage/src/index.ts

// 认证态（设备 ID + 会话上下文 token/session_id）
export {
  getDeviceId,
  setDeviceId,
  clearDeviceId,
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  getToken,
  getSessionId,
} from "./auth-store";
export type { SessionContext } from "./auth-store";

// 加密会话（密钥交换后由 bootstrap 写入，加密拦截器读取）
export {
  setEncryptionSession,
  getEncryptionSession,
  clearEncryptionSession,
} from "./encryption-store";
export type { EncryptionSession } from "./encryption-store";
