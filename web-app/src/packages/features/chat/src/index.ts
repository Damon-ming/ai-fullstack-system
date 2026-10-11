import { registerNS } from "@ming/i18n";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

registerNS("chat-page", en, zh);

export * from './ui'
export * from './hook'
