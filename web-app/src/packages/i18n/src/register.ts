import i18n from "i18next";

/**
 * 注册一个命名空间的词条。
 *
 * 各 feature 模块在入口文件中调用此函数，将自己 locales 下的 en/zh JSON
 * 注册到 i18n 实例。必须在模块顶层调用（side effect），确保 React 组件
 * *useTranslation* 之前词条已就绪。
 *
 * i18next.addResourceBundle 支持 init 之后追加，组件会自动 re-render。
 *
 * @param ns   命名空间（如 "chat-page"）
 * @param en   英文词条对象
 * @param zh   中文词条对象
 */
export function registerNS(
  ns: string,
  en: Record<string, unknown>,
  zh: Record<string, unknown>,
): void {
  // deep=true 允许嵌套词条，overwrite=false 不覆盖已有词条（避免重复注册时意外覆盖）
  i18n.addResourceBundle("en", ns, en, true, false);
  i18n.addResourceBundle("zh", ns, zh, true, false);
}
