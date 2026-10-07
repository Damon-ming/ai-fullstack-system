// web-app/src/packages/biz-common/net/src/auth/device-token.ts
/**
 * 设备 Token 管理 —— 临时方案（无账号系统）
 *
 * TODO: 未来接入账号系统后，改为服务端颁发的 HttpOnly Cookie
 *   - HttpOnly 标志：JS 无法读取，防御 XSS 攻击
 *   - 当前临时方案：前端生成随机 token，通过 Cookie 头发送
 *   - 服务端维护 token 白名单 dict，存在则放行
 *
 * TODO: 设备唯一识别
 *   - 目前用随机 UUID，无法真正识别设备
 *   - 未来可结合：浏览器指纹（canvas/webgl）+ 持久化 localStorage ID + 账号绑定
 *   - 设备指纹用于：同设备免二次验证、异常设备检测
 */

const TOKEN_KEY = "__device_token__";
const TOKEN_BYTE_LENGTH = 32; // 256 bit 随机性，不可预测

/**
 * 获取或创建设备 token。
 * 首次访问时生成并持久化到 localStorage，后续复用。
 */
export function getDeviceToken(): string {
  let token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    token = generateToken();
    localStorage.setItem(TOKEN_KEY, token);
  }
  return token;
}

/**
 * 重新生成 token（用于账号切换或安全重置场景）。
 */
export function resetDeviceToken(): string {
  const token = generateToken();
  localStorage.setItem(TOKEN_KEY, token);
  return token;
}

// ---------------------------------------------------------------------------

function generateToken(): string {
  // 使用 crypto.getRandomValues 生成密码学安全随机数
  const bytes = new Uint8Array(TOKEN_BYTE_LENGTH);
  crypto.getRandomValues(bytes);
  // 转为 hex 字符串存入 cookie
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
