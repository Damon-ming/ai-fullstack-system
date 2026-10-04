// web-app/src/packages/features/upload/src/api/upload.api.ts
import { netClient } from "@ming/biz-common-net-api";
import type { BizRequestConfig, BizResult } from "@ming/biz-common-net-api";
import type { UploadRequest, UploadResponse } from "./types";
import { createLogger } from "@ming/core-log";

const log = createLogger("upload/api");

/** 服务端上传接口实现。请求实体由 hook 层创建并透传。 */
/** @internal */
export async function uploadFile(
  request: UploadRequest,
): Promise<BizResult<UploadResponse>> {
  log.debug("upload request", {
    endpoint: "/api/files/upload/v1",
    fileCount: request.files.length,
  });
  const formData = new FormData();
  request.files.forEach((file) => formData.append("files", file, file.name));
  // PDF 解析、Embedding 和向量入库可能持续几十秒，不能使用普通接口的 10s 超时。
  const cfg: BizRequestConfig = { timeout: 1 * 60 * 1000 };
  const result = await netClient.post<UploadResponse>(
    "/api/files/upload/v1",
    formData,
    cfg,
  );
  log.debug("upload response received");
  return result;
}
