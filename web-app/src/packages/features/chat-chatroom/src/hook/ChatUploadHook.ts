import { useState } from "react";
import { uploadFiles } from "@ming/features-upload-api";

export function chatUploadHook() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const handleFileChange = async (fileList?: FileList | null) => {
    const files = fileList ? Array.from(fileList) : [];
    if (!files.length) return;

    setError("");
    setUploading(true);
    try {
      await uploadFiles(files);
      window.alert("文件上传成功");
    } catch (e) {
      setError(e instanceof Error ? e.message : "文件上传失败");
    } finally {
      setUploading(false);
    }
  };

  return { uploading, error, handleFileChange };
}
