// web-app/src/packages/biz-common/net/src/auth/device-id-store.ts
/**
 * 设备 ID 本地存储 — 服务端下发，客户端缓存并回传。
 *
 * 设备 ID 由服务端根据 UA 计算，客户端只负责：
 *   - 接收并缓存（localStorage）
 *   - 每次请求通过 X-Device-ID header 回传
 *   - 不参与计算（防伪造）
 */

const DEVICE_ID_KEY = "__device_id__";

/**
 * 获取当前缓存的 device_id。
 * 未初始化时返回 null。
 */
export function getDeviceId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(DEVICE_ID_KEY);
}

/**
 * 缓存服务端下发的 device_id。
 */
export function setDeviceId(deviceId: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(DEVICE_ID_KEY, deviceId);
}

/**
 * 清除缓存的 device_id（如重新登录时）。
 */
export function clearDeviceId(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(DEVICE_ID_KEY);
}
