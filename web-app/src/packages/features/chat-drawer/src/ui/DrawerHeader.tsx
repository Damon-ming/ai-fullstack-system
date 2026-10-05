import React from "react";
import { useDrawerHeaderHook } from "../hook/useDrawerHeaderHook";
import { useTranslation } from "@ming/i18n";
import { i18n } from "@ming/i18n";

export const DrawerHeader: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { toggle } = useDrawerHeaderHook();

  const switchLang = () => {
    i18n.changeLanguage(i18n.language === "zh" ? "en" : "zh");
  };

  return (
    <div className="flex items-center justify-between px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-lg">✦</span>
        <strong className="text-sm font-semibold text-slate-800">
          {t("header.brand")}
        </strong>
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={switchLang}
          className="rounded px-1.5 py-0.5 text-xs font-medium text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
        >
          {i18n.language === "zh" ? "EN" : "中文"}
        </button>
        <button
          type="button"
          className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          onClick={toggle}
          aria-label={t("header.collapse")}
        >
          ‹
        </button>
      </div>
    </div>
  );
};
