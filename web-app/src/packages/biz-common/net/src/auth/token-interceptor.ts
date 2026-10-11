// web-app/src/packages/biz-common/net/src/auth/token-interceptor.ts
/**
 * 全局 Token 拦截器 —— 通过内部提供者获取 token，注入 Cookie 头。
 *
 * 不直接依赖 store，token 来源由 bootstrap 通过 setTokenGetter 注入。
 */

import type { NormalizedRequest } from "@ming/core-network";
import { getToken } from "../internal-providers";

const TOKEN_COOKIE_NAME = "device_auth_token";

export function createTokenInterceptor() {
  return {
    onFulfilled: (request: NormalizedRequest): NormalizedRequest => {
      const token = getToken();
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
