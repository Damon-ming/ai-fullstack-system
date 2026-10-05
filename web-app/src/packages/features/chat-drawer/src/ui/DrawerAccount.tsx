import React from "react";
import { useDrawerAccountHook } from "../hook/useDrawerAccountHook";
import { useTranslation } from "@ming/i18n";

export const DrawerAccount: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { account, openAccount } = useDrawerAccountHook();
  return (
    <button
      type="button"
      className="flex items-center gap-3 border-t border-slate-200 px-4 py-3 text-left transition hover:bg-slate-50"
      onClick={() => openAccount(account.name)}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-xs font-semibold text-slate-600">
        {account.avatarText}
      </span>
      <span className="flex flex-col">
        <strong className="text-sm font-medium text-slate-800">
          {account.name}
        </strong>
        <small className="text-xs text-slate-400">
          {t("account.settings")}
        </small>
      </span>
    </button>
  );
};
