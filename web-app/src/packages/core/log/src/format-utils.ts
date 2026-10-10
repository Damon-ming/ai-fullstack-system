// web-app/src/packages/core/log/src/format-utils.ts
/**
 * 日志格式化工具 —— 纯函数，无副作用，可独立使用。
 */

/** 格式化请求体：FormData / Blob / JSON / 其他 → 可读字符串 */
export function formatBody(body: unknown): string {
  if (body === undefined || body === null) return "-";
  if (body instanceof FormData) {
    const entries: string[] = [];
    body.forEach((value, key) => {
      if (value instanceof File) {
        entries.push(`${key}=<File:${value.name}(${value.size}B)>`);
      } else {
        entries.push(`${key}=${String(value).slice(0, 100)}`);
      }
    });
    return `[FormData] ${entries.join(", ")}`;
  }
  if (body instanceof Blob) {
    return `<Blob:${body.size}B>`;
  }
  if (typeof body === "object") {
    try {
      const json = JSON.stringify(body);
      return json.length > 500 ? json.slice(0, 500) + "..." : json;
    } catch {
      return String(body);
    }
  }
  return String(body).slice(0, 200);
}

/** 格式化耗时：毫秒 → 人类可读字符串 */
export function formatTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  // 保留 2 位小数
  return `${(ms / 1000).toFixed(2)}s`;
}
