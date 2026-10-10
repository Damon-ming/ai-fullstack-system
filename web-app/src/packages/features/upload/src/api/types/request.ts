import type { BaseRequest } from "@ming/biz-common-net-api";
export interface UploadRequest extends BaseRequest {
  files: File[];
  /** 文件描述或备注（可选，加密传输） */
  description?: string;
  /** 文件分类，如：合同、发票（可选，加密传输） */
  category?: string;
}
