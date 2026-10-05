import React from "react";
import { useDrawerHeaderHook } from "../hook/useDrawerHeaderHook";
import { useDrawerSearchHook } from "../hook/useDrawerSearchHook";
import { useDrawerNewChatHook } from "../hook/useDrawerNewChatHook";
import { useDrawerUploadHook } from "../hook/useDrawerUploadHook";
import { useTranslation } from "@ming/i18n";

export const DrawerCollapsed: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { toggle } = useDrawerHeaderHook();
  const { openSearch } = useDrawerSearchHook();
  const { newChat } = useDrawerNewChatHook();
  const { handleUpload } = useDrawerUploadHook();

  return (
    <div className="flex flex-col items-center gap-3 py-4">
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        onClick={toggle}
        aria-label={t("header.expand")}
      >
        ☰
      </button>
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        onClick={openSearch}
        aria-label={t("search")}
      >
        ⌕
      </button>
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        onClick={newChat}
        aria-label={t("collapsed.newChat")}
      >
        ＋
      </button>
      <label
        className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        aria-label={t("collapsed.upload")}
      >
        ⌁
        <input
          hidden
          multiple
          type="file"
          accept=".pdf,.xls,.xlsx,.png,.jpg,.jpeg,.csv"
          onChange={(event) => handleUpload(event.target.files)}
        />
      </label>
    </div>
  );
};
