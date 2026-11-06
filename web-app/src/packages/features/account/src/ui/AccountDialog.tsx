// account/src/ui/AccountDialog.tsx
import React from "react";
import { useAccountDialogHook } from "../hook/useAccountDialogHook";
import { useTranslation } from "@ming/i18n";

/**
 * 账户资料编辑弹窗 —— 纯展示组件。
 * 状态与保存编排由 useAccountDialogHook 提供，ui/ 层只做 JSX 渲染。
 */
export function AccountDialog() {
  const { t } = useTranslation("account");
  const { open, draftName, setDraftName, closeDialog, save } =
    useAccountDialogHook();

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-30 grid place-items-center bg-black/40 backdrop-blur-sm"
      onClick={closeDialog}
    >
      <section
        className="w-full max-w-[420px] rounded-2xl bg-white p-6 shadow-2xl"
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="m-0 text-xl font-semibold text-gray-800">
          {t("dialog.title")}
        </h2>
        <p className="mt-1.5 mb-5 text-xs text-gray-400">{t("dialog.hint")}</p>
        <label className="block text-xs font-semibold text-gray-500">
          {t("dialog.displayName")}
          <input
            value={draftName}
            maxLength={30}
            autoFocus
            onChange={(event) => setDraftName(event.target.value)}
            className="mt-2 block w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-gray-700 outline-0 focus:border-blue-400 focus:bg-white"
          />
        </label>
        <div className="mt-5 flex justify-end gap-3">
          <button
            type="button"
            onClick={closeDialog}
            className="rounded-xl bg-gray-100 px-5 py-2 text-gray-500 transition hover:bg-gray-200"
          >
            {t("dialog.cancel")}
          </button>
          <button
            type="button"
            onClick={save}
            className="rounded-xl bg-blue-600 px-5 py-2 font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700"
          >
            {t("dialog.save")}
          </button>
        </div>
      </section>
    </div>
  );
}
