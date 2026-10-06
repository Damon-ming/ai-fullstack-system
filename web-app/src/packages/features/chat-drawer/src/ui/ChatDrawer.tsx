import React from "react";
import { useDrawerHeaderHook } from "../hook/useDrawerHeaderHook";
import { DrawerHeader } from "./DrawerHeader";
import { DrawerNewChat } from "./DrawerNewChat";
import { DrawerUpload } from "./DrawerUpload";
import { DrawerSearch } from "./DrawerSearch";
import { DrawerHistory } from "./DrawerHistory";
import { DrawerAccount } from "./DrawerAccount";
import { DrawerCollapsed } from "./DrawerCollapsed";
import { ErrorBoundary } from "./ErrorBoundary";

export const ChatDrawer: React.FC = () => {
  const { open } = useDrawerHeaderHook();

  return (
    <ErrorBoundary>
      {open ? (
        <aside className="flex h-full w-64 shrink-0 flex-col border-r border-gray-200 bg-gray-100">
          <DrawerHeader />
          <div className="space-y-1 px-2 py-2">
            <DrawerNewChat />
            <DrawerUpload />
            <DrawerSearch />
          </div>
          <DrawerHistory />
          {/* 账号设置始终在最底部 */}
          <div className="mt-auto border-t border-gray-200">
            <DrawerAccount />
          </div>
        </aside>
      ) : (
        <aside className="flex h-full w-14 shrink-0 flex-col border-r border-gray-200 bg-gray-100">
          <DrawerCollapsed />
        </aside>
      )}
    </ErrorBoundary>
  );
};
