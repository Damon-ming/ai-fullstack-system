// chat-drawer/src/ui/DrawerCorpus.tsx
import React from "react";
import { useDrawerCorpusHook } from "../hook/useDrawerCorpusHook";
import { useTranslation } from "@ming/i18n";

export const DrawerCorpus: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const { openCorpus } = useDrawerCorpusHook();

  return (
    <button
      type="button"
      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 transition hover:bg-gray-200 hover:text-gray-700"
      onClick={openCorpus}
    >
      {t("corpus.button")}
    </button>
  );
};
