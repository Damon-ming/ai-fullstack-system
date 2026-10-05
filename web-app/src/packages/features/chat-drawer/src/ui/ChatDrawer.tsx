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
      <aside className="flex h-full w-64 flex-col border-r border-slate-200 bg-white">
        {open ? (
          <>
            <DrawerHeader />
            <div className="space-y-2 py-2">
              <DrawerNewChat />
              <DrawerUpload />
              <DrawerSearch />
            </div>
            <DrawerHistory />
            <DrawerAccount />
          </>
        ) : (
          <DrawerCollapsed />
        )}
      </aside>
    </ErrorBoundary>
  );
};
