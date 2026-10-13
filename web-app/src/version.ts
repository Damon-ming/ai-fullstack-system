// src/version.ts
// 全局版本入口 —— 所有组件 / 模块统一从这里读取版本号。
// 版本真值来源：../package.json，此处只读不写。
import pkg from "../package.json";

export const VERSION = {
  productVersion: pkg.version,
};
