import React from "react";
import { useDrawerNewChatHook } from "../hook/useDrawerNewChatHook";

export const DrawerNewChat: React.FC = () => {
  const { newChat } = useDrawerNewChatHook();
  return (
    <button
      type="button"
      className="mx-3 flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 hover:text-slate-900"
      onClick={newChat}
    >
      ＋ 新建对话
    </button>
  );
};
