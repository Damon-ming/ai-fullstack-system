import { registerNS } from "@ming/i18n";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

registerNS("chat-chatroom", en, zh);

export * from './ui'
export type * from './api/types'
export { chatUploadHook } from './hook'
