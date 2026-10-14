// src/packages/store/src/app-state.ts
/**
 * 全局 App 状态 —— 所有模块共享的基础设施状态
 *
 * 包含：
 *   - token   仅保留 clearToken（用于后期踢出 token 触发刷新）
 *
 * 不包含：
 *   - debug 环境标志 → 直接调用 @ming/biz-common-debug 的 isDebug()
 *   - token / device_id / session_id 存储 → biz-common/storage（auth-store），拦截器直接读取
 *   - 加密会话 → biz-common/storage（encryption-store），拦截器直接读取
 *   - 加密/认证开关 → 拦截器内部通过 isDebug() 运行时决定
 *   - 业务状态 → 在 biz/ 目录下（chat、upload 等）
 *
 * 所有模块通过 @ming/store 统一访问。
 */

import { clearSessionContext } from "@ming/biz-common-storage";
import { createAppStore } from "./app-store";

export interface AppState {
  /** Token —— 仅保留 clearToken（后期踢出 token 时触发刷新） */
  token: {
    clearToken: () => void;
  };
}

export const useAppStore = createAppStore<AppState>(() => ({
  token: {
    clearToken: () => {
      // 原子清除：token + device_id + session_id 同时失效，拦截器不再携带
      clearSessionContext();
      // TODO: 后期可在此触发重新登录流程（事件发布等）
    },
  },
}));
