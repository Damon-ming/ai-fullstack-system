import { useState } from "react";
import { uploadFiles } from "@ming/features-upload-api";
import { useChatUploadStore } from "@ming/store/biz/chat-state";

export function chatUploadHook() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const { startUpload, finishUpload } = useChatUploadStore();

  const handleFileChange = async (fileList?: FileList | null) => {
    const files = fileList ? Array.from(fileList) : [];
    if (!files.length) return;

    setError("");
    setUploading(true);
    startUpload(files.map((f) => f.name));
    try {
      const res = await uploadFiles(files);
      const uploadedFiles = res.data?.files ?? [];
      const duplicateCount = uploadedFiles.filter((f) => f.duplicate).length;
      const indexedCount = uploadedFiles.filter((f) => f.indexed).length;
      const message =
        `${uploadedFiles.length} 个文件上传成功` +
        (duplicateCount > 0 ? `（${duplicateCount} 个已存在）` : "") +
        (indexedCount > 0 ? `，${indexedCount} 个已编入知识库` : "");

      finishUpload("success", message, uploadedFiles);
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : "文件上传失败";
      setError(errMsg);
      finishUpload("error", errMsg);
    } finally {
      setUploading(false);
    }
  };

  return { uploading, error, handleFileChange };
}
