// web-app/src/packages/store/src/biz/upload-state.ts
import { createAppStore } from "../app-store";

// Chat 上传交互状态：只负责上传流程和全局上传弹窗数据。
// 不包含任何文案 —— 文案由 hook/UI 层根据 status + 结果数据通过 i18n 生成。
export type UploadStatus = "idle" | "uploading" | "success" | "error";

export interface ChatUploadFileResult {
  filename: string;
}

export interface ChatUploadFailedFile {
  filename: string;
  error: string;
}

export interface ChatUploadState {
  upload: {
    status: UploadStatus;
    fileNames: string[];
    files: ChatUploadFileResult[];
    failedFiles: ChatUploadFailedFile[];
  };
  startUpload: (fileNames: string[]) => void;
  finishUpload: (
    status: "success" | "error",
    files?: ChatUploadFileResult[],
    failedFiles?: ChatUploadFailedFile[],
  ) => void;
  closeUpload: () => void;
}

export const useChatUploadStore = createAppStore<ChatUploadState>((set) => ({
  upload: { status: "idle", fileNames: [], files: [], failedFiles: [] },
  startUpload: (fileNames) =>
    set({
      upload: { status: "uploading", fileNames, files: [], failedFiles: [] },
    }),
  finishUpload: (status, files = [], failedFiles = []) =>
    set((state) => ({
      upload: { ...state.upload, status, files, failedFiles },
    })),
  closeUpload: () =>
    set((state) => ({ upload: { ...state.upload, status: "idle" } })),
}));
