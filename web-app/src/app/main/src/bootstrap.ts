// src/app/main/src/bootstrap.ts
import { initNetApi } from "@ming/biz-common-net-api";
import { i18n } from "@ming/i18n";

/**
 * 应用最早期执行的全局初始化函数
 * 必须在 ReactDOM.render / createRoot 之前调用并 await 完成
 */
export async function bootstrap(): Promise<void> {
  console.log("[App] Starting initialization...");

  // 1. 最高优先级：初始化网络层
  initGlobalNetwork();

  // 2. 初始化 i18n
  console.log(`[App] i18n initialized, language: ${i18n.language}`);

  console.log("[App] Initialization complete.");
}

/**
 * 全局网络层初始化
 */
function initGlobalNetwork() {
  // 单一环境判断：debug 开日志、关加密；release 开加密、关日志
  const isDebug = import.meta.env.DEV;

  initNetApi({
    baseURL: "",
    timeout: 15000,
    headers: {
      "X-App-Version": "1.0.0",
    },
    enableEncryption: !isDebug,
    enableLogging: isDebug,
    signatureSecret: import.meta.env.VITE_SIGNATURE_SECRET ?? "",
  });

  console.log(
    `[App] 网络层初始化完成 | 加密: ${!isDebug ? "已启用" : "已关闭"} | 日志: ${isDebug ? "已启用" : "已关闭"}`,
  );
}
