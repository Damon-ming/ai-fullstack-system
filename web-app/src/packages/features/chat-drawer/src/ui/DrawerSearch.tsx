import React from "react";
import { useDrawerSearchHook } from "../hook/useDrawerSearchHook";
import { useTranslation } from "@ming/i18n";

export const DrawerSearch: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { openSearch } = useDrawerSearchHook();
  return (
    <button
      type="button"
      className="mx-3 flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
      onClick={openSearch}
    >
      {t("search")}
    </button>
  );
};
