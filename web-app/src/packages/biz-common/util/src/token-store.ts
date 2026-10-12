// web-app/src/packages/biz-common/util/src/token-store.ts
/**
 * Token 本地存储 —— 服务端签发，客户端缓存并回传。
 *
 * Token 由服务端根据手机号计算，客户端只负责：
 *   - 接收并缓存（localStorage）
 *   - 通过 token 拦截器自动携带（Cookie 头）
 *   - 不参与生成（防伪造）
 *
 * 与 device-id-store 同理，纯存取封装，不含业务逻辑。
 */

const TOKEN_KEY = "__device_token__";

/**
 * 获取当前缓存的 token。
 * 未初始化时返回 null。
 */
export function getDeviceToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * 缓存服务端下发的 token。
 */
export function setDeviceToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * 清除缓存的 token（重新登录 / 签发新 token 时调用）。
 */
export function clearDeviceToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}
