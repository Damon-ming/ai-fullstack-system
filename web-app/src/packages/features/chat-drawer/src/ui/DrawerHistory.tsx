import React from "react";
import { useDrawerHistoryHook } from "../hook/useDrawerHistoryHook";
import { useHistoryStore } from "@ming/store/biz/history-state";
import { useTranslation } from "@ming/i18n";

export const DrawerHistory: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { list, groups, activeId, selectChat, deleteHistory } =
    useDrawerHistoryHook();
  const loading = useHistoryStore((s) => s.loading);

  if (loading) {
    return (
      <div className="flex-1 overflow-y-auto px-4 py-2">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-20 rounded bg-slate-200" />
          <div className="h-8 rounded-lg bg-slate-100" />
          <div className="h-8 rounded-lg bg-slate-100" />
          <div className="h-8 rounded-lg bg-slate-100" />
        </div>
        <span className="sr-only">{t("history.loading")}</span>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {t("history.title")}{" "}
        <span className="ml-1 text-slate-300">{list.length}</span>
      </div>
      {groups.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm text-slate-400">
          {t("history.empty")}
        </p>
      ) : (
        <nav className="space-y-4 px-2">
          {groups.map((group) => (
            <React.Fragment key={group.label}>
              <div className="px-2 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                {group.label}
              </div>
              {group.items.map((item) => (
                <div
                  key={item.id}
                  className={`group flex items-center justify-between rounded-lg px-3 py-2 text-sm transition ${
                    activeId === item.id
                      ? "bg-slate-200 font-medium text-slate-900"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => selectChat(item.id)}
                    className="flex min-w-0 flex-1 items-center gap-2 truncate text-left"
                  >
                    ◌ <span className="truncate">{item.title}</span>
                  </button>
                  <button
                    type="button"
                    className="ml-2 hidden h-6 w-6 shrink-0 items-center justify-center rounded text-slate-400 transition hover:bg-slate-200 hover:text-slate-600 group-hover:flex"
                    title={t("history.delete")}
                    aria-label={t("history.delete")}
                    onClick={() => deleteHistory(item.id)}
                  >
                    ×
                  </button>
                </div>
              ))}
            </React.Fragment>
          ))}
        </nav>
      )}
    </div>
  );
};
