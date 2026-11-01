// src/packages/biz-common/net/src/header/language-getter.ts
/**
 * 当前语言 getter —— 解耦 biz-common/net 对 @ming/i18n 的直接依赖。
 *
 * biz-common/net 与 @ming/i18n 是同级模块，不能互相依赖。
 * 通过 setter 注入方式，由 bootstrap 将 i18n.language 的读取函数注册进来。
 *
 * 使用模式（与 app-auth.ts 的 setClearSessionCallback 同构）：
 *   - 默认返回空字符串（未初始化时调用安全）
 *   - bootstrap 阶段通过 setLanguageGetter 注入实际实现
 */

let _languageGetter: () => string = () => "";

export function setLanguageGetter(fn: () => string): void {
  _languageGetter = fn;
}

export function getLanguage(): string {
  return _languageGetter();
}
