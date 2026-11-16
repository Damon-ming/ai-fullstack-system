// web-app/src/packages/features/account/src/hook/session-lifecycle.ts
import {
  clearStoredToken,
  clearEncryptionSession,
} from "@ming/biz-common-storage";
import { useAuthStore } from "@ming/store/biz/auth-state";

/** 清除本地凭据，并发布登录态失效通知。 */
export function invalidateLocalSession(): void {
  clearStoredToken();
  clearEncryptionSession();
  useAuthStore.getState().notifySessionInvalidated();
}
