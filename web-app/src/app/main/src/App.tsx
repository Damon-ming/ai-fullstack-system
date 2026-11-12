// src/app/main/src/App.tsx
import React, { useCallback, useEffect, useState } from "react";
import { DataProvider } from "@ming/data-layer";
import { ChatPage } from "@ming/feature-chat-api";
import { LoginPage } from "@ming/feature-account-api";
import { getSessionContext } from "@ming/biz-common-storage";
import { createLogger } from "@ming/core-log";
import { ensureEncryptionSession } from "./bootstrap";

const log = createLogger("app/App");

type AppView = "loading" | "login" | "chat";

export const App: React.FC = () => {
  const [view, setView] = useState<AppView>("loading");

  useEffect(() => {
    // 启动后检查已有会话：有 token → chat，无 → login
    const session = getSessionContext();
    setView(session?.token ? "chat" : "login");
  }, []);

  /**
   * 登录成功 → 建立加密会话 → 进入主界面。
   *
   * 密钥交换必须在登录之后（需要登录下发的 session_id）。
   * fail-closed：加密开启时交换失败一律留在登录页，不降级为明文进入主界面
   * （debug 也不例外；加密关闭时 ensureEncryptionSession 直接返回，不受影响）。
   */
  const handleLoginSuccess = useCallback(async () => {
    try {
      await ensureEncryptionSession();
    } catch (e) {
      log.error("加密会话建立失败", e);
      return;
    }
    setView("chat");
  }, []);

  if (view === "loading") {
    return (
      <div className="flex h-full w-full items-center justify-center bg-gray-50">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-blue-500" />
      </div>
    );
  }

  if (view === "login") {
    return (
      <DataProvider>
        <LoginPage onSuccess={() => {
          void handleLoginSuccess();
        }} />
      </DataProvider>
    );
  }

  return (
    <DataProvider>
      <ChatPage />
    </DataProvider>
  );
};
