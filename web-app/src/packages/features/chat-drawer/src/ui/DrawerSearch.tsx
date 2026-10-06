import React from "react";
import { useDrawerSearchHook } from "../hook/useDrawerSearchHook";
import { useTranslation } from "@ming/i18n";

export const DrawerSearch: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { openSearch } = useDrawerSearchHook();
  return (
    <button
      type="button"
      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 transition hover:bg-gray-200 hover:text-gray-700"
      onClick={openSearch}
    >
      {t("search")}
    </button>
  );
};
