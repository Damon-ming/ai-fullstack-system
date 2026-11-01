// account/src/index.ts
import { registerNS } from "@ming/i18n";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

registerNS("account", en, zh);

export * from "./api";
export * from "./hook";
export * from "./ui";
