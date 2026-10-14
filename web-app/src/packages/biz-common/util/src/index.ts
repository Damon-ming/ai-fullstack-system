// src/packages/biz-common/util/src/index.ts

// 会话上下文（token + session_id 合一，推荐使用）
export {
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  getToken,
  getSessionId,
} from "./session-context-store";
export type { SessionContext } from "./session-context-store";

// 设备 ID（独立存储，设备生命周期）
export { getDeviceId, setDeviceId, clearDeviceId } from "./device-id-store";

// 加密会话（密钥交换后由 bootstrap 写入，加密拦截器读取）
export {
  setEncryptionSession,
  getEncryptionSession,
  clearEncryptionSession,
} from "./encryption-session-store";
