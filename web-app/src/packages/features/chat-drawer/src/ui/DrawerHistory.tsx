import React from "react";
import { useDrawerHistoryHook } from "../hook/useDrawerHistoryHook";

export const DrawerHistory: React.FC = () => {
  const { list, groups, activeId, selectChat, deleteHistory } =
    useDrawerHistoryHook();

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        最近对话 <span className="ml-1 text-slate-300">{list.length}</span>
      </div>
      <nav className="space-y-4 px-2">
        {groups.map((group) => (
          <React.Fragment key={group.label}>
            <div className="px-2 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              {group.label}
            </div>
            {group.items.map((item) => (
              <div
                role="button"
                tabIndex={0}
                key={item.id}
                className={`group flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm transition ${
                  activeId === item.id
                    ? "bg-slate-200 font-medium text-slate-900"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-800"
                }`}
                onClick={() => selectChat(item.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    selectChat(item.id);
                  }
                }}
              >
                <span className="flex items-center gap-2 truncate">
                  ◌ <span className="truncate">{item.title}</span>
                </span>
                <button
                  type="button"
                  className="ml-2 hidden h-6 w-6 shrink-0 items-center justify-center rounded text-slate-400 transition hover:bg-slate-200 hover:text-slate-600 group-hover:flex"
                  title="删除记录"
                  onClick={(event) => {
                    event.stopPropagation();
                    deleteHistory(item.id);
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </React.Fragment>
        ))}
      </nav>
    </div>
  );
};
