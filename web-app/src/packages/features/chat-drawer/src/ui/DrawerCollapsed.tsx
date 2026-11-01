import React from "react";
import { useDrawerHeaderHook } from "../hook/useDrawerHeaderHook";
import { useDrawerSearchHook } from "../hook/useDrawerSearchHook";
import { useDrawerNewChatHook } from "../hook/useDrawerNewChatHook";
import { useDrawerUploadHook } from "../hook/useDrawerUploadHook";
import { useDrawerKnowledgeHook } from "../hook/useDrawerKnowledgeHook";
import { useTranslation } from "@ming/i18n";

export const DrawerCollapsed: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { toggle } = useDrawerHeaderHook();
  const { openSearch } = useDrawerSearchHook();
  const { newChat } = useDrawerNewChatHook();
  const { handleUpload } = useDrawerUploadHook();
  const { openKnowledge } = useDrawerKnowledgeHook();

  return (
    <div className="flex flex-col items-center gap-2 py-3">
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-200 hover:text-gray-600"
        onClick={toggle}
        aria-label={t("header.expand")}
      >
        ☰
      </button>
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-200 hover:text-gray-600"
        onClick={newChat}
        aria-label={t("collapsed.newChat")}
      >
        ＋
      </button>
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-200 hover:text-gray-600"
        onClick={openSearch}
        aria-label={t("search")}
      >
        ⌕
      </button>
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-200 hover:text-gray-600"
        onClick={openKnowledge}
        aria-label={t("knowledge.button")}
      >
        ⊞
      </button>
      <label
        className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-200 hover:text-gray-600"
        aria-label={t("collapsed.upload")}
      >
        ⌁
        <input
          hidden
          multiple
          type="file"
          accept=".pdf,.md,.txt,.csv,.xlsx,.docx,.doc,.pptx,.html,.htm"
          onChange={(event) => handleUpload(event.target.files)}
        />
      </label>
    </div>
  );
};
