/**
 * 汇总所有 feature 模块的词条资源。
 * 每个模块在 locales/resources.ts 中定义自己的类型，在此合并。
 */
import type { ChatDrawerResources } from "@ming/features-chat-drawer/locales";
import type { ChatPageResources } from "@ming/features-chat/locales";
import type { ChatChatroomResources } from "@ming/features-chat-chatroom/locales";

export interface AppResources {
  "chat-drawer": ChatDrawerResources;
  "chat-page": ChatPageResources;
  "chat-chatroom": ChatChatroomResources;
}

// TypeScript 允许你重新打开（reopen）一个已存在模块的接口并往里加东西，
// 这叫 模块增强 / declaration merging。i18next 官方就预留了 CustomTypeOptions 这个空接口，专门让用户来填充：
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "chat-drawer";
    resources: AppResources;
  }
}
