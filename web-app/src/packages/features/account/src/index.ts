// account/src/index.ts
import { registerNS } from "@ming/i18n";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

registerNS("account", en, zh);

export * from "./api";
export * from "./hook";
export * from "./ui";
// api/ 的 login 是原始 fetcher，hook/ 的 login 是业务编排；包入口显式暴露后者
export { login } from "./hook";
