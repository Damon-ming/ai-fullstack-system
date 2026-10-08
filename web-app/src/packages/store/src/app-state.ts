// web-app/src/packages/store/src/app-state.ts
/**
 * 全局 App 状态 —— 所有模块共享的基础设施状态
 *
 * 只包含两类数据：
 *   - debug：环境标志（isDebug），由 bootstrap 初始化时写入
 *   - token：设备认证令牌，获取后存入
 *
 * 不包含：
 *   - 加密/认证开关 → 由 bootstrap 初始化时通过拦截器注入，逻辑锁死在 biz-common/net
 *   - 业务状态 → 在 biz/ 目录下（chat、upload 等）
 *
 * 所有模块通过 @ming/store 统一访问。
 */

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
}));
