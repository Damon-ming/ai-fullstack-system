import i18n from "i18next";
import { initReactI18next } from "react-i18next";

export const defaultNS = "chat-drawer" as const;

// 初始化时不带资源，各 feature 模块通过 registerNS → addResourceBundle 追加词条。
// i18next 原生支持 init 之后追加资源，组件会自动 re-render 获取新词条。
i18n.use(initReactI18next).init({
  defaultNS,
  lng: "zh",
  fallbackLng: "zh",
  interpolation: { escapeValue: false },
});

export default i18n;
