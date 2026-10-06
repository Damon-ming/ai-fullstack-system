import React from "react";
import { useDrawerNewChatHook } from "../hook/useDrawerNewChatHook";
import { useTranslation } from "@ming/i18n";

export const DrawerNewChat: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { newChat } = useDrawerNewChatHook();
  return (
    <button
      type="button"
      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-200 hover:text-gray-800"
      onClick={newChat}
    >
      {t("newChat")}
    </button>
  );
};
