// src/packages/store/src/app-state.ts
/**
 * 全局 App 状态 —— 所有模块共享的基础设施状态
 *
 * 包含：
 *   - debug：环境标志（isDebug），由 bootstrap 初始化时写入
 *   - token：设备认证令牌，获取后存入
 *   - encryption：加密会话（密钥交换后由 bootstrap 写入）
 *
 * 不包含：
 *   - 加密/认证开关 → 由 bootstrap 初始化时通过拦截器注入，逻辑锁死在 biz-common/net
 *   - 业务状态 → 在 biz/ 目录下（chat、upload 等）
 *
 * 所有模块通过 @ming/store 统一访问。
 */

import type { EncryptionSession } from "@ming/biz-common-net-api";
import { createAppStore } from "./app-store";

export interface AppState {
  /** 环境标志：true = debug，false = release */
  debug: {
    isDebug: boolean;
  };
  /** 设备认证令牌 */
  token: {
    deviceToken: string | null;
    setDeviceToken: (token: string | null) => void;
    clearToken: () => void;
  };
  /** 加密会话（密钥交换后由 bootstrap 写入，拦截器读取） */
  encryption: {
    session: EncryptionSession | null;
    setSession: (session: EncryptionSession | null) => void;
  };
}

export const useAppStore = createAppStore<AppState>((set) => ({
  debug: {
    isDebug: false, // bootstrap 启动时覆盖
  },
  token: {
    deviceToken: null,
    setDeviceToken: (deviceToken) =>
      set((state) => ({ token: { ...state.token, deviceToken } })),
    clearToken: () =>
      set((state) => ({ token: { ...state.token, deviceToken: null } })),
  },
  // 这是关键。它返回一个新的 encryption 对象，替换掉旧的。
  // ...state.encryption → 把旧的 encryption 里的所有字段先展开
  // session → 用新的 session 覆盖（等价于 session: session）
  // 所以整体意思是："把 encryption 里的 session 更新为新值，其他字段保持不变。"
  encryption: {
    session: null, // bootstrap 密钥交换后写入
    setSession: (session) =>
      set((state) => ({ encryption: { ...state.encryption, session } })),
  },
}));
