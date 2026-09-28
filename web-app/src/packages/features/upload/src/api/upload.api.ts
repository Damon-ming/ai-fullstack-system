// web-app/src/packages/features/upload/src/api/upload.api.ts
import { dataApi } from "@ming/data-layer";
import type { DataApiResponse } from "@ming/data-layer";
import type { UploadRequest, UploadResponse } from "./types";
import { createLogger } from "@ming/core-log";

const log = createLogger("upload/api");

/** 服务端上传接口实现。请求实体由 hook 层创建并透传。 */
/** @internal */
export async function uploadFile(
  request: UploadRequest,
): Promise<DataApiResponse<UploadResponse>> {
  log.debug("upload request", {
    endpoint: "/api/files/upload/v1",
    fileCount: request.files.length,
  });
  const formData = new FormData();
  request.files.forEach((file) => formData.append("files", file, file.name));
  try {
    // PDF 解析、Embedding 和向量入库可能持续几十秒，不能使用普通接口的 10s 超时。
    const response = await dataApi.post<UploadResponse>(
      "/api/files/upload/v1",
      formData,
      {
        timeout: 1 * 60 * 1000,
      },
    );
    log.debug("upload response received");
    return response;
  } catch (error) {
    log.error("upload request failed", error);
    throw error;
  }
}
