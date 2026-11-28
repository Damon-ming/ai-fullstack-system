// account/src/hook/useAccountDialogHook.ts
import { useAccountStore } from "@ming/store/biz/account-state";
import { useAccount } from "./AccountHook";
import { logout as logoutApi } from "../api";
import { invalidateLocalSession } from "./session-lifecycle";
import { useState } from "react";
import { useTranslation } from "@ming/i18n";

/**
 * 账户资料编辑弹窗 —— 订阅 store 中的弹窗状态，编排保存流程。
 *
 * 弹窗开关/草稿是跨模块 UI 状态，统一放在 @ming/store（推模式）；
 * 本 hook 是 account 模块内读取该状态并发起保存的唯一发起层。
 */
export function useAccountDialogHook() {
  const open = useAccountStore((s) => s.dialogOpen);
  const draftNickname = useAccountStore((s) => s.draftNickname);
  const setDraftNickname = useAccountStore((s) => s.setDraftNickname);
  const closeDialog = useAccountStore((s) => s.closeDialog);
  const { update } = useAccount(false);
  const { t } = useTranslation("account");
  const [logoutError, setLogoutError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (saving) return;
    setSaveError("");
    setSaving(true);
    try {
      await update(draftNickname);
      closeDialog();
    } catch {
      setSaveError(t("dialog.saveError"));
    } finally {
      setSaving(false);
    }
  };

  const logout = async () => {
    setLogoutError("");
    try {
      await logoutApi();
      invalidateLocalSession();
      closeDialog();
    } catch {
      setLogoutError(t("dialog.logoutError"));
    }
  };

  return {
    open,
    draftNickname,
    setDraftNickname,
    closeDialog,
    save,
    saveError,
    saving,
    logout,
    logoutError,
  };
}
