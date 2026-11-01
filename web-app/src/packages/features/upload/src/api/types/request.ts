import type { BaseRequest } from "@ming/biz-common-net-api";
export interface UploadRequest extends BaseRequest {
  files: File[];
}
