import { useState } from "react";
import { uploadFiles } from "@ming/feature-upload-api";
import { useChatUploadStore } from "@ming/store/biz/upload-state";

/**
 * @deprecated 使用 useDrawerUploadHook 替代，该 hook 支持 i18n。
 * 保留此 hook 以维持 chat-chatroom 包的导出兼容性。
 */
export function chatUploadHook() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const startUpload = useChatUploadStore((s) => s.startUpload);
  const finishUpload = useChatUploadStore((s) => s.finishUpload);

  const handleFileChange = async (fileList?: FileList | null) => {
    const files = fileList ? Array.from(fileList) : [];
    if (!files.length) return;

    setError("");
    setUploading(true);
    startUpload(files.map((f) => f.name));
    try {
      const res = await uploadFiles(files);
      const successFiles = res?.success_files ?? [];
      const duplicateFiles = res?.duplicate_files ?? [];
      const failedFiles = res?.failed_files ?? [];
      finishUpload("success", successFiles, duplicateFiles, failedFiles);
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : "CLIENT:Upload failed";
      setError(errMsg);
      finishUpload("error");
    } finally {
      setUploading(false);
    }
  };

  return { uploading, error, handleFileChange };
}
