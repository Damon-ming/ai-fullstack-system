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
    deleteConfirmationId,
    requestDeleteHistory,
    cancelDeleteHistory,
    confirmDeleteHistory,
    pin,
    unpin,
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
    return (
      <div className="flex-1 overflow-y-auto px-4 py-8">
        <p className="text-center text-sm text-gray-400">
          {t("history.empty")}
        </p>
      </div>
    );
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
              {group.isPinnedGroup ? t("history.pinned") : group.label}
            </div>
            {group.items.map((item) => (
              <div
                key={item.conversationId}
                className={`group flex h-9 w-full items-center rounded-lg text-sm transition ${
                  activeConversationId === item.conversationId
                    ? "bg-blue-50 font-medium text-blue-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                <button
                  type="button"
                  onClick={() => selectChat(item.conversationId)}
                  className="h-full min-w-0 flex-1 truncate px-3 text-left"
                >
                  {item.title}
                </button>
                {item.isPinned ? (
                  <button
                    type="button"
                    title={t("history.unpin")}
                    aria-label={t("history.unpin")}
                    onClick={() => unpin(item.conversationId)}
                    className="h-full px-2 text-blue-600 hover:text-gray-400"
                  >
                    📌
                  </button>
                ) : (
                  <button
                    type="button"
                    title={t("history.pin")}
                    aria-label={t("history.pin")}
                    onClick={() => pin(item.conversationId)}
                    className="h-full px-2 text-gray-400 hover:text-blue-600"
                  >
                    📌
                  </button>
                )}
                <button
                  type="button"
                  title={t("history.delete")}
                  aria-label={t("history.delete")}
                  onClick={() => requestDeleteHistory(item.conversationId)}
                  className="h-full px-2 text-gray-400 opacity-0 transition-opacity hover:text-red-600 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
                >
                  🗑️
                </button>
              </div>
            ))}
          </React.Fragment>
        ))}
      </nav>
      {isLoadingMore && (
        <div className="py-2 text-center text-xs text-gray-400">
          {t("history.loading")}
        </div>
      )}
      {deleteConfirmationId && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/40 backdrop-blur-sm"
          onClick={cancelDeleteHistory}
        >
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="history-delete-title"
            aria-describedby="history-delete-message"
            className="mx-4 w-full max-w-[420px] rounded-2xl bg-white p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h2
              id="history-delete-title"
              className="text-lg font-semibold text-gray-800"
            >
              {t("history.deleteConfirmTitle")}
            </h2>
            <p
              id="history-delete-message"
              className="mt-2 text-sm text-gray-500"
            >
              {t("history.deleteConfirmMessage")}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                autoFocus
                onClick={cancelDeleteHistory}
                className="rounded-xl bg-gray-100 px-5 py-2 text-gray-600 transition hover:bg-gray-200"
              >
                {t("history.cancel")}
              </button>
              <button
                type="button"
                onClick={confirmDeleteHistory}
                className="rounded-xl bg-red-600 px-5 py-2 font-semibold text-white transition hover:bg-red-700"
              >
                {t("history.confirmDelete")}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
};
