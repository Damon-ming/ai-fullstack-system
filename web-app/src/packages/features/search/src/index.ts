import { registerNS } from "@ming/i18n";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

registerNS("search", en, zh);

export * from "./api";
export * from "./hook";
export * from "./ui";
