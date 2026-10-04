// web-app/src/packages/store/src/biz/upload-state.ts
import { createAppStore } from "../app-store";

// Chat 上传交互状态：只负责上传流程和全局上传弹窗数据。
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
    message: string;
    fileNames: string[];
    files: ChatUploadFileResult[];
  };
  startUpload: (fileNames: string[]) => void;
  finishUpload: (
    status: "success" | "error",
    message: string,
    files?: ChatUploadFileResult[],
  ) => void;
  closeUpload: () => void;
}

export const useChatUploadStore = createAppStore<ChatUploadState>((set) => ({
  upload: { status: "idle", message: "", fileNames: [], files: [] },
  startUpload: (fileNames) =>
    set({
      upload: {
        status: "uploading",
        message: "正在上传文件，请稍候…",
        fileNames,
        files: [],
      },
    }),
  finishUpload: (status, message, files = []) =>
    set((state) => ({ upload: { ...state.upload, status, message, files } })),
  closeUpload: () =>
    set((state) => ({
      upload: { ...state.upload, status: "idle", message: "" },
    })),
}));
