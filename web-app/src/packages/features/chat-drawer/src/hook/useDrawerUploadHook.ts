import { useMemo, useRef, useCallback } from "react";
import { uploadFiles as uploadFilesFromApi } from "@ming/features-upload-api";
import { useChatUploadStore } from "@ming/store/biz/upload-state";
import { useTranslation } from "@ming/i18n";
import { createLogger } from "@ming/core-log";

const log = createLogger("chat-drawer/upload");

export function useDrawerUploadHook() {
  const { t } = useTranslation("chat-drawer");
  const upload = useChatUploadStore((s) => s.upload);
  const startUpload = useChatUploadStore((s) => s.startUpload);
  const finishUpload = useChatUploadStore((s) => s.finishUpload);
  const closeUpload = useChatUploadStore((s) => s.closeUpload);

  /** 当前进行中的上传控制器，用于主动取消 */
  const abortControllerRef = useRef<AbortController | null>(null);

  /** 取消当前进行中的上传 */
  const abortUpload = useCallback(() => {
    if (abortControllerRef.current) {
      log.debug("abortUpload triggered");
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

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

    // 为本次上传创建独立的控制器（先取消上一次，防止并发）
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    startUpload(files.map((file) => file.name));
    const [err, response] = await uploadFilesFromApi(files, controller.signal);
    if (controller.signal.aborted) {
      log.debug("upload aborted by user");
      closeUpload();
      return;
    }
    abortControllerRef.current = null;
    if (err) {
      finishUpload("error");
    } else {
      const resultFiles = Array.isArray(response?.data?.files)
        ? response.data.files
        : [];
      finishUpload("success", resultFiles);
    }
  };

  return { upload, message, handleUpload, abortUpload };
}
