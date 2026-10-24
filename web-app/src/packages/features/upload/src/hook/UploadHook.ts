// web-app/src/packages/features/upload/src/hook/UploadHook.ts
import { uploadFile as requestUploadFile } from "../api";
import type { UploadRequest, UploadResponse } from "../api/types";
import { createLogger } from "@ming/core-log";

const log = createLogger("upload/hook");

export interface UploadMeta {
  description?: string;
  category?: string;
}

// ── 上传限制常量（与后端 upload-config.yaml 保持一致）─────────────────
const MAX_FILES_PER_REQUEST = 10;

// 各类型文件大小上限（字节），与后端 allowed_types 一一对应
const FILE_TYPE_LIMITS: Record<string, number> = {
  pdf: 50 * 1024 * 1024, // 50MB
  md: 10 * 1024 * 1024, // 10MB
  txt: 10 * 1024 * 1024, // 10MB
  csv: 10 * 1024 * 1024, // 10MB
  xlsx: 50 * 1024 * 1024, // 50MB
  docx: 20 * 1024 * 1024, // 20MB
  doc: 20 * 1024 * 1024, // 20MB
  pptx: 50 * 1024 * 1024, // 50MB
  html: 5 * 1024 * 1024, // 5MB
  htm: 5 * 1024 * 1024, // 5MB
};

// 支持的扩展名正则
const ALLOWED_EXTENSIONS = /\.(pdf|md|txt|csv|xlsx|docx|doc|pptx|html|htm)$/i;

// 允许的扩展名列表（用于错误提示）
const ALLOWED_EXTENSIONS_LIST =
  ".pdf, .md, .txt, .csv, .xlsx, .docx, .doc, .pptx, .html";

function createUploadRequest(files: File[], meta?: UploadMeta): UploadRequest {
  if (!files.length) throw new Error("至少选择一个文件");

  if (files.length > MAX_FILES_PER_REQUEST) {
    throw new Error(
      `单次最多上传 ${MAX_FILES_PER_REQUEST} 个文件，当前 ${files.length} 个`,
    );
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
): Promise<UploadResponse> {
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
