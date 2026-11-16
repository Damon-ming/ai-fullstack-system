// src/app/main/src/bootstrap.ts
import {
  initNetApi,
  setLanguageGetter,
  decryptSsePayload,
} from "@ming/biz-common-net-api";
import { createLogger } from "@ming/core-log";
import {
  isDebug,
  initDebugEnv,
  isEncryptionEnabled,
} from "@ming/biz-common-debug";
import { i18n } from "@ming/i18n";
import {
  setEncryptionSession,
  getEncryptionSession,
  getStoredToken,
} from "@ming/biz-common-storage";
import { exchangeKeys } from "@ming/feature-encryption-api";
import { createAuthInterceptors } from "@ming/feature-account-api";

const log = createLogger("app/bootstrap");

/**
 * 应用最早期执行的全局初始化函数
 * 必须在 ReactDOM.render / createRoot 之前调用并 await 完成
 */
export async function bootstrap(): Promise<void> {
  log.info("Starting initialization...");

  // 0. 初始化环境标志（开发构建下读取 localStorage 覆盖，生产构建为 no-op）
  initDebugEnv();

  // 注册语言 getter（setter 注入，解耦 biz-common/net → i18n）
  setLanguageGetter(() => i18n.language);

  // 1. 最高优先级：初始化网络层
  await initGlobalNetwork();

  // 2. 初始化 i18n
  log.info(`i18n initialized, language: ${i18n.language}`);

  // 3. 登录改为 UI 流程（LoginPage），不再自动登录
  log.info("Initialization complete.");
}

/**
 * 全局网络层初始化
 *
 * 通过 isEncryptionEnabled 判断开关，一次性注入拦截器：
 *   release:          加密开、日志关
 *   debug（开关关）:  加密关、日志开
 *   debug（开关开）:  加密开、日志开
 *
 * 启动阶段不做密钥交换：交换需要登录后的 token，
 * 未登录时调用必然失败。仅在检测到已有登录态（刷新恢复）时补建。
 */
async function initGlobalNetwork(): Promise<void> {
  const debug = isDebug();
  const encryptionOn = isEncryptionEnabled();
  const authInterceptors = createAuthInterceptors();

  initNetApi({
    baseURL: "",
    timeout: 15000,
    enableEncryption: encryptionOn,
    // SSE 响应不经加密中间件，解密钩子由客户端在解析阶段就地完成
    sseDecryptData: encryptionOn ? decryptSsePayload : undefined,
    enableLogging: debug,
    interceptors: { response: authInterceptors.restResponse },
    sseResponseHeadersInterceptors: authInterceptors.sseResponseHeaders,
  });

  // 已登录（页面刷新恢复会话）时补建加密会话；未登录交给登录成功入口。
  // fail-closed：加密开启时交换失败一律中止启动，debug 也不例外 ——
  // debug 只放宽「要不要加密」，不放宽「加密失败要不要容忍」。
  if (encryptionOn) {
    try {
      await ensureEncryptionSession();
    } catch (error) {
      // 认证业务码已由账号模块清除过期登录态；正常进入登录页。
      if (getStoredToken()) throw error;
      log.info("已保存的登录态失效，等待用户重新登录");
    }
  }

  log.info(
    `网络层初始化完成 | debug=${debug} | 加密: ${encryptionOn ? "开" : "关"} | 日志: ${debug ? "开" : "关"}`,
  );
}

/**
 * 确保加密会话存在（已登录且开启加密时）。
 *
 * 密钥交换必须在登录之后：/api/encryption/session/v1 需要 token，
 * 服务端自行查出内部 session_id。登录成功与页面刷新恢复都调用本函数。
 *
 * 幂等：已有未过期会话时直接返回，不重复交换。
 */
export async function ensureEncryptionSession(): Promise<void> {
  if (!isEncryptionEnabled()) return;

  if (!getStoredToken()) return;

  const existing = await getEncryptionSession();
  if (existing) return;

  const session = await exchangeKeys();
  await setEncryptionSession(session);
  log.info("加密会话已建立", { key_id: session.keyId });
}
