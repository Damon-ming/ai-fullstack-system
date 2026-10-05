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
  // 统一通过 Nginx 的 /api 反向代理访问后端，避免 80 与 8000 端口跨域。
  initNetApi({
    baseURL: "",
    timeout: 15000,
    headers: {
      "X-App-Version": "1.0.0",
    },
  });

  // 提示：如果 initNetApi 需要动态注入 token，可以在这里或全局拦截器中配置
}
