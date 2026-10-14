// src/app/main/src/bootstrap.ts
import { initNetApi } from "@ming/biz-common-net-api";
import { createLogger } from "@ming/core-log";
import { isDebug } from "@ming/biz-common-debug";
import { i18n } from "@ming/i18n";
import { setEncryptionSession } from "@ming/biz-common-storage";
import { initDeviceToken } from "@ming/feature-account-api";
import { exchangeKeys } from "@ming/feature-encryption-api";
import { useAppStore } from "@ming/store";

const log = createLogger("app/bootstrap");

/**
 * 应用最早期执行的全局初始化函数
 * 必须在 ReactDOM.render / createRoot 之前调用并 await 完成
 */
export async function bootstrap(): Promise<void> {
  log.info("Starting initialization...");

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
  // 将环境标志写入全局 app-state
  //TODO: 上线记得删除这个写法，改为从服务端获取
  useAppStore.setState({ debug: { isDebug } });

  initNetApi({
    baseURL: "",
    timeout: 15000,
    enableEncryption: !isDebug,
    enableAuth: !isDebug,
    enableLogging: isDebug,
  });

  // release 模式时，token 初始化和密钥交换必须成功
  if (!isDebug) {
    // 加密会话 → 写入 app-state，加密拦截器自动加解密
    // 签名密钥已在 exchangeKeys 内部通过 HKDF 派生，存储在 session.signatureKeyHex

    const session = await exchangeKeys();
    await setEncryptionSession(session);
    log.info("加密会话初始化完成", { key_id: session.keyId });
  }

  log.info(
    `网络层初始化完成 | debug=${isDebug} | 加密: ${!isDebug ? "开" : "关"} | 认证: ${!isDebug ? "开" : "关"} | 日志: ${isDebug ? "开" : "关"}`,
  );
}
