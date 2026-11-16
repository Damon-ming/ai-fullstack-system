import { createAppStore } from "../app-store";

/** 只记录登录态失效通知，不保存凭据或页面状态。 */
export interface AuthState {
  sessionInvalidationVersion: number;
  notifySessionInvalidated: () => void;
}

export const useAuthStore = createAppStore<AuthState>((set) => ({
  sessionInvalidationVersion: 0,
  notifySessionInvalidated: () =>
    set((state) => ({
      sessionInvalidationVersion: state.sessionInvalidationVersion + 1,
    })),
}));
