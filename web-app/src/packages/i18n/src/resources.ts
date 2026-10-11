/**
 * 汇总所有 feature 模块的词条资源。
 * 每个模块在 locales/resources.ts 中定义自己的类型，在此合并。
 *
 * 使用 import type + 相对路径，编译后不产生运行时依赖。
 * i18n 的 package.json 中不声明 feature 依赖，避免循环。
 */
import type { ChatDrawerResources } from "../../features/chat-drawer/src/locales/resources";
import type { ChatPageResources } from "../../features/chat/src/locales/resources";
import type { ChatChatroomResources } from "../../features/chat-chatroom/src/locales/resources";

export interface AppResources {
  "chat-drawer": ChatDrawerResources;
  "chat-page": ChatPageResources;
  "chat-chatroom": ChatChatroomResources;
}

// TypeScript 允许重新打开一个已存在模块的接口并往里加东西，
// 这叫模块增强 / declaration merging。i18next 官方预留了 CustomTypeOptions
// 这个空接口，专门让用户来填充：
// "TypeScript 啊，请打开 node_modules/i18next 这个包的类型定义，往它的 CustomTypeOptions 接口里加字段。"
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "chat-drawer";
    resources: AppResources;
  }
}
