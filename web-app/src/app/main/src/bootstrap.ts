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
  // release 环境默认开启加密，debug 环境可通过 .env 手动开启
  const enableEncryption =
    import.meta.env.VITE_ENABLE_ENCRYPTION === "true" ||
    (!import.meta.env.DEV && import.meta.env.VITE_ENABLE_ENCRYPTION !== "false");

  initNetApi({
    baseURL: "",
    timeout: 15000,
    headers: {
      "X-App-Version": "1.0.0",
    },
    enableEncryption,
  });

  console.log(`[App] 网络层初始化完成 | 加密: ${enableEncryption ? "已启用" : "已关闭"}`);
}
