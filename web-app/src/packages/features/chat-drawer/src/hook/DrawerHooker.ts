import { useHistory } from "@ming/features-history-api";
import { uploadFiles as uploadFilesFromApi } from "@ming/features-upload-api";
import {
  useChatUiStore,
  useChatMessageStore,
  useChatUploadStore,
} from "@ming/store/biz/chat-state";
import { useSearchStore } from "@ming/store/biz/search-state";
import { useAccountStore } from "@ming/store/biz/account-state";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerHook() {
  const open = useChatUiStore((state) => state.drawerOpen);
  const toggle = useChatUiStore((state) => state.toggleDrawer);
  const resetSession = useChatUiStore((state) => state.resetSession);
  const resetMessages = useChatMessageStore((state) => state.resetMessages);
  const setMessages = useChatMessageStore((state) => state.setMessages);
  const revision = useHistoryStore((state) => state.revision);
  const activeId = useHistoryStore((state) => state.activeId);
  const setActiveId = useHistoryStore((state) => state.setActiveId);
  const beginLoad = useHistoryStore((state) => state.beginLoad);
  const refreshHistory = useHistoryStore((state) => state.notifyChanged);
  const { list, groups, getMessages, remove } = useHistory(revision);
  const account = useAccountStore((state) => state.profile) ?? {
    id: "murphy",
    name: "Murphy",
    avatarText: "M",
  };
  const openSearch = useSearchStore((state) => state.openSearch);
  const openAccount = useAccountStore((state) => state.openDialog);
  const upload = useChatUploadStore((state) => state.upload);
  const startUpload = useChatUploadStore((state) => state.startUpload);
  const finishUpload = useChatUploadStore((state) => state.finishUpload);
  const newChat = () => {
    resetMessages();
    resetSession();
    setActiveId(null);
  };
  const selectChat = (id: string) => {
    beginLoad();
    setMessages(getMessages(id));
    setActiveId(id);
    resetSession();
  };
  const uploadFiles = async (fileList?: FileList | null) => {
    const files = fileList ? Array.from(fileList) : [];
    if (!files.length) return;
    startUpload(files.map((file) => file.name));
    try {
      const response = await uploadFilesFromApi(files);
      if (response.bizCode >= 40000) throw new Error("服务端返回上传失败");
      const resultFiles = Array.isArray(response.data?.files)
        ? response.data.files
        : [];
      const allIndexed =
        resultFiles.length === 0 ||
        resultFiles.every((file) => file.indexed || file.duplicate);
      finishUpload(
        "success",
        allIndexed ? "文件已经进入语料库" : "文件已上传，部分词条仍在更新",
        resultFiles,
      );
    } catch (error) {
      finishUpload(
        "error",
        error instanceof Error ? error.message : "文件上传失败",
      );
    }
  };
  const deleteHistory = (id: string) => {
    remove(id);
    refreshHistory();
  };
  return {
    open,
    toggle,
    list,
    groups,
    activeId,
    account,
    openSearch,
    openAccount,
    upload,
    newChat,
    selectChat,
    uploadFiles,
    deleteHistory,
  };
}
