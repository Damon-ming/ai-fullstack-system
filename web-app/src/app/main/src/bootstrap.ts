// src/app/main/src/bootstrap.ts
import { initNetApi } from "@ming/biz-common-net-api";
import { createLogger } from "@ming/core-log";
import { isDebug, initDebugEnv } from "@ming/biz-common-debug";
import { i18n } from "@ming/i18n";
import { setEncryptionSession } from "@ming/biz-common-storage";
import { initDeviceToken } from "@ming/feature-account-api";
import { exchangeKeys } from "@ming/feature-encryption-api";

const log = createLogger("app/bootstrap");

/**
 * 应用最早期执行的全局初始化函数
 * 必须在 ReactDOM.render / createRoot 之前调用并 await 完成
 */
export async function bootstrap(): Promise<void> {
  log.info("Starting initialization...");

  // 0. 初始化环境标志（开发构建下读取 localStorage 覆盖，生产构建为 no-op）
  initDebugEnv();

  // 1. 最高优先级：初始化网络层
  await initGlobalNetwork();

  // 2. 初始化 i18n
  log.info(`i18n initialized, language: ${i18n.language}`);

  // 3. 初始化设备 Token（hook 层已处理 localStorage 写入）
  await initDeviceToken();

  log.info("Initialization complete.");
}

/**
 * 全局网络层初始化
 *
 * 通过 isDebug 判断开关，一次性注入拦截器：
 *   debug:    加密关、日志开、认证关
 *   release:  加密开、日志关、认证开
 *
 * release 模式下，token 初始化和密钥交换必须成功，否则抛错中止启动。
 */
async function initGlobalNetwork(): Promise<void> {
  const debug = isDebug();

  initNetApi({
    baseURL: "",
    timeout: 15000,
    enableEncryption: !debug,
    enableAuth: !debug,
    enableLogging: debug,
  });

  // release 模式时，token 初始化和密钥交换必须成功
  if (!debug) {
    const session = await exchangeKeys();
    await setEncryptionSession(session);
    log.info("加密会话初始化完成", { key_id: session.keyId });
  }

  log.info(
    `网络层初始化完成 | debug=${debug} | 加密: ${!debug ? "开" : "关"} | 认证: ${!debug ? "开" : "关"} | 日志: ${debug ? "开" : "关"}`,
  );
}
