// src/packages/store/src/app-auth.ts
/**
 * 认证回调注册 —— 解耦 store 层与 biz-common-storage 的直接依赖。
 *
 * store 层（全局状态）不应直接 import biz-common-storage（同级模块），
 * 因此通过 setter 注入方式，由 app 启动时将 clearSessionContext 注册进来。
 *
 * 使用模式：
 *   - 默认 no-op（未初始化时调用安全）
 *   - bootstrap 阶段通过 setClearSessionCallback 注入实际实现
 */

let _clearSessionCallback: () => void = () => {};

export function setClearSessionCallback(fn: () => void): void {
  _clearSessionCallback = fn;
}

export function clearSession(): void {
  _clearSessionCallback();
}
