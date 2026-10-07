// src/app/main/src/bootstrap.ts
import { initNetApi } from "@ming/biz-common-net-api";
import { useDebugStore } from "@ming/debug";
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
 *
 * 单一环境判断派生所有开关：
 *   debug:    加密关、日志开、认证关、CORS 全放行（前后端联调）
 *   release:  加密开、日志关、认证开、CORS 限制域名
 */
function initGlobalNetwork() {
  // 从全局 debug store 读取环境（后续所有模块统一从这里获取）
  const isDebug = useDebugStore.getState().isDebug;

  initNetApi({
    baseURL: "",
    timeout: 15000,
    headers: {
      "X-App-Version": "1.0.0",
    },
    // 安全开关（debug 关加密开日志，release 开加密关日志）
    enableEncryption: !isDebug,
    enableAuth: !isDebug,
    enableLogging: isDebug,
    // 签名密钥（加密关闭时留空）
    signatureSecret: import.meta.env.VITE_SIGNATURE_SECRET ?? "",
  });

  console.log(
    `[App] 网络层初始化完成 | 加密: ${!isDebug ? "已启用" : "已关闭"} | 认证: ${!isDebug ? "已启用" : "已关闭"} | 日志: ${isDebug ? "已启用" : "已关闭"}`,
  );
}
