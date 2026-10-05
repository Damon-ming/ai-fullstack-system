// web-app/src/packages/store/src/biz/upload-state.ts
import { createAppStore } from "../app-store";

// Chat 上传交互状态：只负责上传流程和全局上传弹窗数据。
// 不包含任何文案 —— 文案由 hook/UI 层根据 status + 结果数据通过 i18n 生成。
export type UploadStatus = "idle" | "uploading" | "success" | "error";

export interface ChatUploadFileResult {
  filename: string;
  file_md5: string;
  file_size: number;
  duplicate: boolean;
  indexed: boolean;
}

export interface ChatUploadState {
  upload: {
    status: UploadStatus;
    /** 已完成上传的文件数量（用于 UI 判断是否全部 indexed） */
    fileNames: string[];
    files: ChatUploadFileResult[];
  };
  startUpload: (fileNames: string[]) => void;
  finishUpload: (
    status: "success" | "error",
    files?: ChatUploadFileResult[],
  ) => void;
  closeUpload: () => void;
}

export const useChatUploadStore = createAppStore<ChatUploadState>((set) => ({
  upload: { status: "idle", fileNames: [], files: [] },
  startUpload: (fileNames) =>
    set({ upload: { status: "uploading", fileNames, files: [] } }),
  finishUpload: (status, files = []) =>
    set((state) => ({ upload: { ...state.upload, status, files } })),
  closeUpload: () =>
    set((state) => ({ upload: { ...state.upload, status: "idle" } })),
}));
