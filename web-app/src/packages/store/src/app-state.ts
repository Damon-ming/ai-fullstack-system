// src/packages/store/src/app-state.ts
/**
 * 全局 App 状态 —— 所有模块共享的基础设施状态
 *
 * 包含：
 *   - debug   环境标志（isDebug），由 bootstrap 初始化时写入
 *   - token   仅保留 clearToken（用于后期踢出 token 触发刷新）
 *
 * 不包含：
 *   - token / device_id / session_id 存储 → localStorage（session-context-store），拦截器直接读取
 *   - 加密会话 → localStorage（encryption-session-store），拦截器直接读取
 *   - 加密/认证开关 → 由 bootstrap 初始化时通过拦截器注入，逻辑锁死在 biz-common/net
 *   - 业务状态 → 在 biz/ 目录下（chat、upload 等）
 *
 * 所有模块通过 @ming/store 统一访问。
 */

import { clearSessionContext } from "@ming/biz-common-util";
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
}

export const useAppStore = createAppStore<AppState>((set) => ({
  debug: {
    isDebug: false, // bootstrap 启动时覆盖
  },
  token: {
    clearToken: () => {
      // 原子清除：token + device_id + session_id 同时失效，拦截器不再携带
      clearSessionContext();
      // TODO: 后期可在此触发重新登录流程（事件发布等）
    },
  },
}));
