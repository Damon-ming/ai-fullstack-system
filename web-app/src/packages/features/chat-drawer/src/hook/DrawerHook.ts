import { useDrawerHeaderHook } from "./useDrawerHeaderHook";
import { useDrawerNewChatHook } from "./useDrawerNewChatHook";
import { useDrawerUploadHook } from "./useDrawerUploadHook";
import { useDrawerSearchHook } from "./useDrawerSearchHook";
import { useDrawerHistoryHook } from "./useDrawerHistoryHook";
import { useDrawerAccountHook } from "./useDrawerAccountHook";

/** 兼容旧用法 —— 组合所有子 hook 暴露统一接口 */
export function useDrawerHook() {
  const header = useDrawerHeaderHook();
  const newChat = useDrawerNewChatHook();
  const upload = useDrawerUploadHook();
  const search = useDrawerSearchHook();
  const history = useDrawerHistoryHook();
  const account = useDrawerAccountHook();

  return {
    open: header.open,
    toggle: header.toggle,
    list: history.list,
    groups: history.groups,
    activeId: history.activeId,
    account: account.account,
    openSearch: search.openSearch,
    openAccount: account.openAccount,
    upload: upload.upload,
    newChat: newChat.newChat,
    selectChat: history.selectChat,
    uploadFiles: upload.handleUpload,
    deleteHistory: history.deleteHistory,
  };
}
