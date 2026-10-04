import { uploadFile as requestUploadFile } from "../api";
import type { BizResult } from "@ming/biz-common-net-api";
import type { UploadRequest, UploadResponse } from "../api/types";
import { createLogger } from "@ming/core-log";

const log = createLogger("upload/hook");

function createUploadRequest(files: File[]): UploadRequest {
  if (!files.length) throw new Error("至少选择一个文件");
  const allowedTypes = new Set([
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png",
    "image/jpeg",
    "text/csv",
  ]);
  const allowedExtensions = /\.(pdf|xls|xlsx|png|jpe?g|csv)$/i;
  if (
    files.some(
      (file) =>
        !allowedTypes.has(file.type) && !allowedExtensions.test(file.name),
    )
  ) {
    throw new Error("仅支持 PDF、Excel、PNG、JPEG、CSV 文件");
  }
  if (files.some((file) => file.size > 10 * 1024 * 1024))
    throw new Error("单个大小不能超过 10MB");
  return { files };
}

export async function uploadFiles(
  files: File[],
): Promise<BizResult<UploadResponse>> {
  log.debug("upload started", {
    fileCount: files.length,
    fileNames: files.map((file) => file.name),
  });
  const result = await requestUploadFile(createUploadRequest(files));
  log.debug("upload finished", { fileCount: files.length });
  return result;
}
