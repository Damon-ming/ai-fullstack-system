// src/packages/biz-common/net/src/version.ts
/**
 * 前端系统版本号 —— 与后端 SYSTEM_VERSION 对应。
 *
 * 用于：
 *   - 通过 X-System-Version header 随每次请求上报，服务端可据此做兼容/统计
 *   - 日志标记，方便排查版本相关问题
 */
export const SYSTEM_VERSION = "1.0.0";
