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

  // meta_json 包含文件描述/分类等业务参数，由加密拦截器读取并加密。
  // 即使为空对象也要传入，否则加密拦截器无法区分"无 meta"和"漏传 meta"。
  const meta: Record<string, string> = {};
  if (request.description) meta.description = request.description;
  if (request.category) meta.category = request.category;
  formData.set("meta_json", JSON.stringify(meta));

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
