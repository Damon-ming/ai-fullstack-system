// web-app/src/packages/features/upload/src/hook/UploadHook.ts
import { uploadFile as requestUploadFile, isFailure } from "../api";
import type { UploadRequest, UploadResponse } from "../api";
import { createLogger } from "@ming/core-log";

const log = createLogger("upload/hook");

// ── 上传限制常量（与后端 upload-config.yaml 保持一致）─────────────────
const MAX_FILES_PER_REQUEST = 10;
const MAX_TOTAL_UPLOAD_SIZE = 50 * 1024 * 1024; // 50MB

// 各类型文件大小上限（字节），与后端 allowed_types 一一对应
const FILE_TYPE_LIMITS: Record<string, number> = {
  pdf: 10 * 1024 * 1024, // 10MB
  md: 10 * 1024 * 1024, // 10MB
  txt: 10 * 1024 * 1024, // 10MB
  csv: 10 * 1024 * 1024, // 10MB
  xlsx: 10 * 1024 * 1024, // 10MB
  xls: 10 * 1024 * 1024, // 10MB
  docx: 10 * 1024 * 1024, // 10MB
  doc: 10 * 1024 * 1024, // 10MB
  pptx: 10 * 1024 * 1024, // 10MB
  ppt: 10 * 1024 * 1024, // 10MB
  html: 10 * 1024 * 1024, // 10MB
  htm: 10 * 1024 * 1024, // 10MB
  bmp: 5 * 1024 * 1024, // 5MB
  jpeg: 5 * 1024 * 1024, // 5MB
  jpg: 5 * 1024 * 1024, // 5MB
  png: 5 * 1024 * 1024, // 5MB
  tif: 5 * 1024 * 1024, // 5MB
  tiff: 5 * 1024 * 1024, // 5MB
};

const ALLOWED_EXTENSIONS = new RegExp(
  `\\.(${Object.keys(FILE_TYPE_LIMITS).join("|")})$`,
  "i",
);

export const UPLOAD_ACCEPT = Object.keys(FILE_TYPE_LIMITS)
  .map((extension) => `.${extension}`)
  .join(",");

const ALLOWED_EXTENSIONS_LIST = UPLOAD_ACCEPT.split(",").join(", ");

function createUploadRequest(files: File[]): UploadRequest {
  if (!files.length) throw new Error("至少选择一个文件");

  if (files.length > MAX_FILES_PER_REQUEST) {
    throw new Error(
      `单次最多上传 ${MAX_FILES_PER_REQUEST} 个文件，当前 ${files.length} 个`,
    );
  }

  const totalSize = files.reduce((total, file) => total + file.size, 0);
  if (totalSize > MAX_TOTAL_UPLOAD_SIZE) {
    throw new Error("单次上传文件总大小不能超过 50MB");
  }

  if (files.some((file) => !ALLOWED_EXTENSIONS.test(file.name))) {
    throw new Error(`仅支持 ${ALLOWED_EXTENSIONS_LIST} 文件`);
  }

  // 按类型校验文件大小
  for (const file of files) {
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    const limit = FILE_TYPE_LIMITS[ext];
    if (limit && file.size > limit) {
      const mb = Math.round(limit / (1024 * 1024));
      throw new Error(`文件 "${file.name}" 超过 ${mb}MB 限制`);
    }
  }

  return { files };
}

export async function uploadFiles(
  files: File[],
  signal?: AbortSignal,
): Promise<UploadResponse> {
  log.debug("upload started", {
    fileCount: String(files.length),
    fileNames: files.map((file) => file.name).join(", "),
  });
  const result = await requestUploadFile(createUploadRequest(files), signal);
  if (isFailure(result.code)) {
    log.error("upload failed", { code: result.code });
    throw new Error(`上传失败: ${result.code}`);
  }
  log.debug("upload finished", { fileCount: files.length });
  return result.data!;
}
