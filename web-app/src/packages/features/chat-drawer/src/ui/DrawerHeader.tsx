import React from "react";
import { useDrawerHeaderHook } from "../hook/useDrawerHeaderHook";
import { useTranslation } from "@ming/i18n";

export const DrawerHeader: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { toggle } = useDrawerHeaderHook();

  return (
    <div className="flex items-center justify-between px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-base text-blue-500">✦</span>
        <strong className="text-sm font-semibold text-gray-800">
          {t("header.brand")}
        </strong>
      </div>
      <button
        type="button"
        className="flex h-7 w-7 items-center justify-center rounded-md text-gray-400 transition hover:bg-gray-200 hover:text-gray-600"
        onClick={toggle}
        aria-label={t("header.collapse")}
      >
        ‹
      </button>
    </div>
  );
};
