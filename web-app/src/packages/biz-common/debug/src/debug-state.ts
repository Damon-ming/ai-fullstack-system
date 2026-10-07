// web-app/src/packages/biz-common/debug/src/debug-state.ts
/**
 * Debug 全局状态 —— 运行时环境标志 + 调试开关
 *
 * 职责：
 *   - 集中管理 "当前是否为 debug 环境" 这一事实（只读，跟随构建环境）
 *   - 提供运行时调试开关（如：强制加密、强制认证 —— 用于在 debug 环境模拟 release 行为）
 *
 * 设计说明：
 *   - isDebug 是构建时确定的，不可运行时修改
 *   - overrides 是运行时可调的，用于联调测试
 *   - 其他模块通过 useDebugStore 读取环境，而非各自调用 import.meta.env.DEV
 */

import { createAppStore } from "@ming/store";

export interface DebugState {
  /** 构建环境标志：true = debug（Vite DEV），false = release（Vite PROD） */
  readonly isDebug: boolean;

  /**
   * 运行时覆盖开关 —— 在 debug 环境模拟 release 行为
   * 例：debug 联调时打开 forceEncryption，测试加密链路
   */
  overrides: {
    /** 强制启用加密（仅 isDebug=true 时有效） */
    forceEncryption: boolean;
    /** 强制启用认证（仅 isDebug=true 时有效） */
    forceAuth: boolean;
  };

  // ==== 动作 ============================================================

  /** 设置覆盖开关 */
  setOverride: (key: keyof DebugState["overrides"], value: boolean) => void;
  /** 重置所有覆盖开关 */
  resetOverrides: () => void;
}

/**
 * 全局 Debug 单例 Store。
 *
 * isDebug 在创建时固化，后续不可变。
 * overrides 可通过 setOverride 在运行时修改（用于联调）。
 */
export const useDebugStore = createAppStore<DebugState>((set) => ({
  isDebug: import.meta.env.DEV,
  overrides: {
    forceEncryption: false,
    forceAuth: false,
  },
  setOverride: (key, value) =>
    set((state) => ({
      overrides: { ...state.overrides, [key]: value },
    })),
  resetOverrides: () =>
    set({
      overrides: {
        forceEncryption: false,
        forceAuth: false,
      },
    }),
}));

// ==== 派生选择器（方便业务层使用）====================================

/** 实际是否启用加密（release 始终开，debug 看覆盖开关） */
export function selectEnableEncryption(state: DebugState): boolean {
  if (!state.isDebug) return true; // release 始终加密
  return state.overrides.forceEncryption; // debug 看覆盖
}

/** 实际是否启用认证（release 始终开，debug 看覆盖开关） */
export function selectEnableAuth(state: DebugState): boolean {
  if (!state.isDebug) return true; // release 始终认证
  return state.overrides.forceAuth; // debug 看覆盖
}

/** 实际是否启用日志（debug 默认开，release 始终关） */
export function selectEnableLogging(state: DebugState): boolean {
  return state.isDebug && !state.overrides.forceAuth; // 联调认证时不打印日志避免干扰
}
