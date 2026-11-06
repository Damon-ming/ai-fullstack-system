// account/src/hook/useAccountDialogHook.ts
import { useAccountStore } from "@ming/store/biz/account-state";
import { useAccount } from "./AccountHook";

/**
 * 账户资料编辑弹窗 —— 订阅 store 中的弹窗状态，编排保存流程。
 *
 * 弹窗开关/草稿是跨模块 UI 状态，统一放在 @ming/store（推模式）；
 * 本 hook 是 account 模块内读取该状态并发起保存的唯一发起层。
 */
export function useAccountDialogHook() {
  const open = useAccountStore((s) => s.dialogOpen);
  const draftName = useAccountStore((s) => s.draftName);
  const setDraftName = useAccountStore((s) => s.setDraftName);
  const closeDialog = useAccountStore((s) => s.closeDialog);
  const { update } = useAccount();

  const save = () => {
    void update(draftName);
    closeDialog();
  };

  return { open, draftName, setDraftName, closeDialog, save };
}
