import { ErrorCode } from "@ming/biz-common-net-api";
import { invalidateLocalSession } from "./session-lifecycle";

/** 只有服务端明确判定登录凭据失效时才退出；普通 401 不代表登录失效。 */
function handleAuthError(code: number): void {
  if (
    code === ErrorCode.AUTH.MISSING_TOKEN ||
    code === ErrorCode.AUTH.INVALID_TOKEN ||
    code === ErrorCode.AUTH.INVALID_SESSION
  ) {
    invalidateLocalSession();
  }
}

function getBusinessCode(body: unknown): number | null {
  if (body === null || typeof body !== "object" || !("code" in body)) return null;
  const code = body.code;
  return typeof code === "number" ? code : null;
}

/** 注册到全局网络配置；REST 和 SSE 只共享认证策略，不改动网络层。 */
export function createAuthInterceptors() {
  return {
    restResponse: {
      onRejected: (error: unknown): unknown => {
        const response = (error as { response?: { status?: number; data?: unknown } })?.response;
        if (response?.status === 401) {
          const code = getBusinessCode(response.data);
          if (code !== null) handleAuthError(code);
        }
        return error;
      },
    },
    sseResponseHeaders: {
      onFulfilled: async (response: Response): Promise<void> => {
        if (response.status !== 401) return;
        try {
          const code = getBusinessCode(await response.clone().json());
          if (code !== null) handleAuthError(code);
        } catch {
          // 非 JSON 401 没有认证业务码，交给原有 SSE 错误处理。
        }
      },
    },
  };
}
