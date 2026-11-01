// chat-drawer/src/ui/DrawerKnowledge.tsx
import React from "react";
import { useKnowledgeStore } from "@ming/store";
import { useTranslation } from "@ming/i18n";

export const DrawerKnowledge: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const openKnowledge = useKnowledgeStore((s) => s.openKnowledge);

  return (
    <button
      type="button"
      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 transition hover:bg-gray-200 hover:text-gray-700"
      onClick={openKnowledge}
    >
      {t("knowledge.button")}
    </button>
  );
};
