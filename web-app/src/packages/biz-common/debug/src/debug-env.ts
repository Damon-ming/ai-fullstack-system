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
const ENCRYPTION_TOGGLE_KEY = "__encryption_toggle__";

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

// ---------------------------------------------------------------------------
// 加密开关（仅开发构建可调）
// ---------------------------------------------------------------------------

/**
 * debug 下的加解密开关（默认关）。
 *
 * 由服务端策略主导：release 恒为 true（配置层面不允许关闭），
 * debug 由本开关决定，便于本地调试明文 / 密文两种链路。
 */
export function isEncryptionToggleOn(): boolean {
  if (!BUILD_DEFAULT) return false;
  return get(ENCRYPTION_TOGGLE_KEY) === "true";
}

export function setEncryptionToggle(on: boolean): void {
  if (!BUILD_DEFAULT) return;
  set(ENCRYPTION_TOGGLE_KEY, String(on));
}

/**
 * 加解密开关（服务端主导）。
 *
 *   release: 恒开 —— 服务端 fail-closed，未声明加密直接拒绝
 *   debug:   由 localStorage 开关决定（默认关，保持现状）
 *
 * 开关只影响「客户端是否发送密文」，服务端策略始终优先。
 * 定义在本模块而非 app 层：两个原语（isDebug / isEncryptionToggleOn）
 * 都在这里，派生值跟着原语走。
 */
export function isEncryptionEnabled(): boolean {
  return !isDebug() || isEncryptionToggleOn();
}
