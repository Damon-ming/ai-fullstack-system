// web-app/src/packages/features/account/src/hook/session-lifecycle.ts
import {
  clearStoredToken,
  clearEncryptionSession,
} from "@ming/biz-common-storage";
import { useAuthStore } from "@ming/store/biz/auth-state";
import { useEffect } from "react";

/** 清除本地凭据，并发布登录态失效通知。 */
export function invalidateLocalSession(): void {
  clearStoredToken();
  clearEncryptionSession();
  useAuthStore.getState().notifySessionInvalidated();
}

/** 订阅登录态失效通知；页面如何响应由调用方决定。 */
export function useSessionInvalidation(onInvalidated: () => void): void {
  useEffect(
    () =>
      useAuthStore.subscribe((state, previous) => {
        if (state.sessionInvalidationVersion !== previous.sessionInvalidationVersion) {
          onInvalidated();
        }
      }),
    [onInvalidated],
  );
}
