// web-app/src/packages/biz-common/debug/src/debug-env.ts
/**
 * Debug 环境检测 —— 纯工具，不持有状态。
 *
 * 职责：
 *   - 检测当前是否为 debug 环境（构建时确定）
 *
 * 状态由全局 app-state 持有，bootstrap 初始化时写入。
 */

/** 当前是否为 debug 环境（构建时确定，运行时不可变） */
export const isDebug = import.meta.env.DEV;

/** 当前环境字符串 */
export const envName = isDebug ? "debug" : "release";

/**
 * 环境数值编码 —— 用于 X-Client-Env 请求头。
 * 0 = debug，1 = release（服务端据此判断客户端环境）
 */
export const envCode = isDebug ? 0 : 1;

/**
 * 客户端类型编码 —— 用于 X-Client-Type 请求头。
 * 0 = 浏览器，1 = 移动端（预留）
 */
export const clientTypeCode = 0;
