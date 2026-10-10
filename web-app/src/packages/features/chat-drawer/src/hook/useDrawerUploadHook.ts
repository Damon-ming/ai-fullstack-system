import { useMemo } from "react";
import { uploadFiles as uploadFilesFromApi } from "@ming/features-upload-api";
import { useChatUploadStore } from "@ming/store/biz/upload-state";
import { useTranslation } from "@ming/i18n";

export function useDrawerUploadHook() {
  const { t } = useTranslation("chat-drawer");
  const upload = useChatUploadStore((s) => s.upload);
  const startUpload = useChatUploadStore((s) => s.startUpload);
  const finishUpload = useChatUploadStore((s) => s.finishUpload);

  // 根据 status + 结果数据生成 i18n 文案
  const message = useMemo(() => {
    switch (upload.status) {
      case "uploading":
        return t("upload.uploading");
      case "error":
        return t("upload.error");
      case "success": {
        const allIndexed = upload.files.every((f) => f.indexed || f.duplicate);
        return allIndexed
          ? t("upload.success_allIndexed")
          : t("upload.success_partial");
      }
      default:
        return t("upload.idle");
    }
  }, [upload.status, upload.files, t]);

  const handleUpload = async (fileList?: FileList | null) => {
    const files = fileList ? Array.from(fileList) : [];
    if (!files.length) return;
    startUpload(files.map((file) => file.name));
    const [err, response] = await uploadFilesFromApi(files);
    if (err) {
      finishUpload("error");
    } else {
      const resultFiles = Array.isArray(response?.data?.files)
        ? response.data.files
        : [];
      finishUpload("success", resultFiles);
    }
  };

  return { upload, message, handleUpload };
}
