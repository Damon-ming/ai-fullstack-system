// web-app/src/packages/features/upload/src/hook/UploadHook.ts
import { uploadFile as requestUploadFile } from "../api";
import type { BizResult } from "@ming/biz-common-net-api";
import type { UploadRequest, UploadResponse } from "../api/types";
import { createLogger } from "@ming/core-log";

const log = createLogger("upload/hook");

export interface UploadMeta {
  description?: string;
  category?: string;
}

function createUploadRequest(files: File[], meta?: UploadMeta): UploadRequest {
  if (!files.length) throw new Error("至少选择一个文件");
  const allowedExtensions = /\.(pdf|md|txt)$/i;
  if (files.some((file) => !allowedExtensions.test(file.name))) {
    throw new Error("仅支持 PDF、Markdown、TXT 文件");
  }
  if (files.some((file) => file.size > 10 * 1024 * 1024))
    throw new Error("单个大小不能超过 10MB");
  return {
    files,
    description: meta?.description,
    category: meta?.category,
  };
}

export async function uploadFiles(
  files: File[],
  meta?: UploadMeta,
  signal?: AbortSignal,
): Promise<BizResult<UploadResponse>> {
  log.debug("upload started", {
    fileCount: String(files.length),
    fileNames: files.map((file) => file.name).join(", "),
    hasMeta: String(!!meta),
  });
  const result = await requestUploadFile(
    createUploadRequest(files, meta),
    signal,
  );
  log.debug("upload finished", { fileCount: files.length });
  return result;
}
