// src/app/main/src/App.tsx
import React, { useEffect, useState } from "react";
import { DataProvider } from "@ming/data-layer";
import { ChatPage } from "@ming/feature-chat-api";
import { LoginPage } from "@ming/feature-account-api";
import { getSessionContext } from "@ming/biz-common-storage";

type AppView = "loading" | "login" | "chat";

export const App: React.FC = () => {
  const [view, setView] = useState<AppView>("loading");

  useEffect(() => {
    // 启动后检查已有会话：有 token → chat，无 → login
    const session = getSessionContext();
    setView(session?.token ? "chat" : "login");
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
        <LoginPage onSuccess={() => setView("chat")} />
      </DataProvider>
    );
  }

  return (
    <DataProvider>
      <ChatPage />
    </DataProvider>
  );
};
