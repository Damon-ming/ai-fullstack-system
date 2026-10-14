// web-app/src/packages/biz-common/debug/src/debug-env.ts
/**
 * 环境标志模块 —— 构建时默认值 + 运行时初始化。
 *
 * 使用方式：
 *   bootstrap 阶段调用 initDebugEnv()，一次性读取 localStorage 覆盖并缓存。
 *   后续通过 isDebug() / envCode() / envName() 获取。
 *
 * 安全约束：
 *   生产构建（BUILD_DEFAULT=false）时 initDebugEnv() 为 no-op，
 *   isDebug() 永远返回 false，localStorage 覆盖无效。
 */

import { get, set, remove } from "@ming/core-storage";

const DEBUG_OVERRIDE_KEY = "__debug_override__";

/** 构建时默认值（不可变底线） */
const BUILD_DEFAULT = import.meta.env.DEV;

/** 缓存的调试标志，由 initDebugEnv() 初始化 */
let cachedDebug: boolean | undefined;

// ---------------------------------------------------------------------------
// 初始化（bootstrap 注入入口）
// ---------------------------------------------------------------------------

/**
 * 初始化环境标志。
 *
 * 在 bootstrap 阶段调用一次。开发构建下读取 localStorage 覆盖值并缓存；
 * 生产构建下为 no-op（import.meta.env.DEV 有值，注入无效）。
 */
export function initDebugEnv(): void {
  // 生产构建：import.meta.env.DEV 为 false，注入无效
  if (!BUILD_DEFAULT) {
    cachedDebug = false;
    return;
  }
  // 开发构建：读取 localStorage 显式覆盖（core/storage 已内置 SSR 兜底）
  const raw = get(DEBUG_OVERRIDE_KEY);
  cachedDebug = raw === null ? BUILD_DEFAULT : raw === "true";
}

// ---------------------------------------------------------------------------
// 读取
// ---------------------------------------------------------------------------

/** 获取当前是否为调试环境 */
export function isDebug(): boolean {
  // 未初始化时回退到构建默认值（SSR 兜底）
  if (cachedDebug === undefined) return BUILD_DEFAULT;
  return cachedDebug;
}

export function envCode(): number {
  return isDebug() ? 0 : 1;
}

export function envName(): string {
  return isDebug() ? "debug" : "release";
}

/** 客户端类型编码 —— 浏览器 = 0，移动端 = 1（预留） */
export function clientTypeCode(): number {
  return 0;
}

// ---------------------------------------------------------------------------
// 写入（仅开发构建有效）
// ---------------------------------------------------------------------------

export function setDebug(value: boolean): void {
  if (!BUILD_DEFAULT) return;
  set(DEBUG_OVERRIDE_KEY, String(value));
  cachedDebug = value;
}

export function clearDebugOverride(): void {
  if (!BUILD_DEFAULT) return;
  remove(DEBUG_OVERRIDE_KEY);
  cachedDebug = BUILD_DEFAULT;
}
