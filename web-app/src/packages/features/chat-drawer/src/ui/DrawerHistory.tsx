// web-app/src/packages/features/chat-drawer/src/ui/DrawerHistory.tsx
import React from "react";
import { useDrawerHistoryHook } from "../hook/useDrawerHistoryHook";
import { useTranslation } from "@ming/i18n";

export const DrawerHistory: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const {
    list,
    groups,
    activeConversationId,
    loading,
    selectChat,
    hasMore,
    loadMore,
    isLoadingMore,
  } = useDrawerHistoryHook();

  // 滚动接近底部时加载下一页：历史会话可能远超首屏加载的 20 条
  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = event.currentTarget;
    if (hasMore && scrollHeight - scrollTop - clientHeight < 40) {
      loadMore();
    }
  };

  if (loading) {
    return (
      <div className="flex-1 overflow-y-auto px-4 py-2">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-20 rounded bg-gray-200" />
          <div className="h-8 rounded-lg bg-gray-100" />
          <div className="h-8 rounded-lg bg-gray-100" />
          <div className="h-8 rounded-lg bg-gray-100" />
        </div>
        <span className="sr-only">{t("history.loading")}</span>
      </div>
    );
  }

  if (list.length === 0) {
    return null;
  }

  return (
    <div className="flex-1 overflow-y-auto" onScroll={handleScroll}>
      <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
        {t("history.title")}{" "}
        <span className="ml-1 text-gray-300">{list.length}</span>
      </div>
      <nav className="space-y-3 px-2">
        {groups.map((group) => (
          <React.Fragment key={group.label}>
            <div className="px-2 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              {group.label}
            </div>
            {group.items.map((item) => (
              <button
                key={item.conversationId}
                type="button"
                onClick={() => selectChat(item.conversationId)}
                className={`flex h-9 w-full items-center rounded-lg px-3 text-sm text-left transition ${
                  activeConversationId === item.conversationId
                    ? "bg-blue-50 font-medium text-blue-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                <span className="truncate">{item.title}</span>
              </button>
            ))}
          </React.Fragment>
        ))}
      </nav>
      {isLoadingMore && (
        <div className="py-2 text-center text-xs text-gray-400">
          {t("history.loading")}
        </div>
      )}
    </div>
  );
};
