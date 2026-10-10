// src/app/main/src/bootstrap.ts
import { initNetApi } from "@ming/biz-common-net-api";
import { createLogger } from "@ming/core-log";
import { isDebug } from "@ming/debug";
import { i18n } from "@ming/i18n";
import { useAppStore } from "@ming/store";

const log = createLogger("app/bootstrap");

/**
 * 应用最早期执行的全局初始化函数
 * 必须在 ReactDOM.render / createRoot 之前调用并 await 完成
 */
// eslint-disable-next-line @typescript-eslint/require-await
export async function bootstrap(): Promise<void> {
  log.info("Starting initialization...");

  // 1. 最高优先级：初始化网络层
  initGlobalNetwork();

  // 2. 初始化 i18n
  log.info(`i18n initialized, language: ${i18n.language}`);

  log.info("Initialization complete.");
}

/**
 * 全局网络层初始化
 *
 * 通过 isDebug 判断开关，一次性注入拦截器：
 *   debug:    加密关、日志开、认证关
 *   release:  加密开、日志关、认证开
 */
function initGlobalNetwork() {
  // 将环境标志写入全局 app-state
  useAppStore.setState({ debug: { isDebug } });

  initNetApi({
    baseURL: "",
    timeout: 15000,
    headers: {
      "X-App-Version": "1.0.0",
    },
    enableEncryption: !isDebug,
    enableAuth: !isDebug,
    enableLogging: isDebug,
    signatureSecret: import.meta.env.VITE_SIGNATURE_SECRET ?? "",
  });

  log.info(
    `网络层初始化完成 | debug=${isDebug} | 加密: ${!isDebug ? "开" : "关"} | 认证: ${!isDebug ? "开" : "关"} | 日志: ${isDebug ? "开" : "关"}`,
  );
}
