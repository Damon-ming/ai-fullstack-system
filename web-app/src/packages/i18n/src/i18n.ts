import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enDrawer from "@ming/features-chat-drawer/locales/en.json";
import zhDrawer from "@ming/features-chat-drawer/locales/zh.json";
import enChat from "@ming/features-chat/locales/en.json";
import zhChat from "@ming/features-chat/locales/zh.json";
import enChatroom from "@ming/features-chat-chatroom/locales/en.json";
import zhChatroom from "@ming/features-chat-chatroom/locales/zh.json";

export const defaultNS = "chat-drawer" as const;

export const resources = {
  en: {
    "chat-drawer": enDrawer,
    "chat-page": enChat,
    "chat-chatroom": enChatroom,
  },
  zh: {
    "chat-drawer": zhDrawer,
    "chat-page": zhChat,
    "chat-chatroom": zhChatroom,
  },
  // 加 as const
  // const b = { name: "Tom" } as const;
  // 类型: { readonly name: "Tom" }
  // b.name = "Jerry";   // ❌ 报错：Cannot assign to 'name' because it is a read-only property
} as const;

// {
//   "greeting": "Hello, {{name}}!"
// }
// t("greeting", { name: "Tom" });
// → "Hello, Tom!"

//escapeValue: true（默认）
// t("greeting", { name: "<b>Tom</b>" });
// → "Hello, &lt;b&gt;Tom&lt;/b&gt;!"

// escapeValue: false
// t("greeting", { name: "<b>Tom</b>" });
// → "Hello, <b>Tom</b>!"
i18n.use(initReactI18next).init({
  defaultNS,
  resources,
  lng: "zh",
  fallbackLng: "zh",
  interpolation: { escapeValue: false },
});

export default i18n;
