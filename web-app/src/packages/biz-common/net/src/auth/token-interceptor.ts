// web-app/src/packages/biz-common/net/src/auth/token-interceptor.ts
/**
 * 全局 Token 拦截器 —— 从 app-state 读取 token 注入 Cookie 头。
 */

import type { NormalizedRequest } from "@ming/core-network";
import { useAppStore } from "@ming/store";

const TOKEN_COOKIE_NAME = "device_auth_token";

export function createTokenInterceptor() {
  return {
    onFulfilled: (request: NormalizedRequest): NormalizedRequest => {
      const token = useAppStore.getState().token.deviceToken;
      if (!token) return request;

      return {
        ...request,
        headers: {
          ...request.headers,
          Cookie: `${TOKEN_COOKIE_NAME}=${token}`,
        },
      };
    },
  };
}
