// src/packages/store/src/app-state.ts
/**
 * 全局 App 状态 —— 所有模块共享的基础设施状态
 *
 * 包含：
 *   - debug   环境标志（isDebug），由 bootstrap 初始化时写入
 *   - token   仅保留 clearToken（用于后期踢出 token 触发刷新）
 *   - encryption  加密会话（密钥交换后由 bootstrap 写入，拦截器读取）
 *
 * 不包含：
 *   - token 存储 → localStorage（biz-common/util/token-store），拦截器直接读取
 *   - device_id   → localStorage（biz-common/util/device-id-store），拦截器直接读取
 *   - 加密/认证开关 → 由 bootstrap 初始化时通过拦截器注入，逻辑锁死在 biz-common/net
 *   - 业务状态 → 在 biz/ 目录下（chat、upload 等）
 *
 * 所有模块通过 @ming/store 统一访问。
 */

import type { EncryptionSession } from "@ming/biz-common-net-api";
import { clearDeviceToken } from "@ming/biz-common-util";
import { createAppStore } from "./app-store";

export interface AppState {
  /** 环境标志：true = debug，false = release */
  debug: {
    isDebug: boolean;
  };
  /** Token —— 仅保留 clearToken（后期踢出 token 时触发刷新） */
  token: {
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
    clearToken: () => {
      // 清除 localStorage 中的 token，拦截器不再携带
      clearDeviceToken();
      // TODO: 后期可在此触发重新登录流程（事件发布等）
    },
  },
  encryption: {
    session: null, // bootstrap 密钥交换后写入
    setSession: (session) =>
      set((state) => ({ encryption: { ...state.encryption, session } })),
  },
}));
