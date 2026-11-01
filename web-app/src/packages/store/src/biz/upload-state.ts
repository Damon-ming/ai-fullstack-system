// web-app/src/packages/store/src/biz/upload-state.ts
import { createAppStore } from "../app-store";

// Chat 上传交互状态：只负责上传流程和全局上传弹窗数据。
// 不包含任何文案 —— 文案由 hook/UI 层根据 status + 结果数据通过 i18n 生成。
export type UploadStatus = "idle" | "uploading" | "success" | "error";

export interface ChatUploadFileResult {
  filename: string;
  file_uid: string;
}

export interface ChatUploadDuplicateFile {
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
    successFiles: ChatUploadFileResult[];
    duplicateFiles: ChatUploadDuplicateFile[];
    failedFiles: ChatUploadFailedFile[];
  };
  startUpload: (fileNames: string[]) => void;
  finishUpload: (
    status: "success" | "error",
    successFiles?: ChatUploadFileResult[],
    duplicateFiles?: ChatUploadDuplicateFile[],
    failedFiles?: ChatUploadFailedFile[],
  ) => void;
  closeUpload: () => void;
}

export const useChatUploadStore = createAppStore<ChatUploadState>((set) => ({
  upload: {
    status: "idle",
    fileNames: [],
    successFiles: [],
    duplicateFiles: [],
    failedFiles: [],
  },
  startUpload: (fileNames) =>
    set({
      upload: {
        status: "uploading",
        fileNames,
        successFiles: [],
        duplicateFiles: [],
        failedFiles: [],
      },
    }),
  finishUpload: (
    status,
    successFiles = [],
    duplicateFiles = [],
    failedFiles = [],
  ) =>
    set((state) => ({
      upload: {
        ...state.upload,
        status,
        successFiles,
        duplicateFiles,
        failedFiles,
      },
    })),
  closeUpload: () =>
    set((state) => ({ upload: { ...state.upload, status: "idle" } })),
}));
