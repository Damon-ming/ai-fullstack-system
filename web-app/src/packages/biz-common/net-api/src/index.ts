// src/packages/biz-common/net-api/index.ts

export { initNetApi } from "./init";
export { netClient } from "./net-client";
export type { INetClient } from "@ming/biz-common-net"; // re-export 接口
// 网络层类型继续从这里导出（这一层本来就是类型门面）
export type {
  BizApiSuccessResponse,
  BizApiErrorResponse,
  BizResult,
  BaseRequest,
  BizRequestConfig,
  BizRequestCallbacks,
  SseStreamOptions,
  SseRequestOptions,
  SseStreamCallbacks,
  SseFinalState,
  SseStreamStatus,
} from "@ming/biz-common-net";
export { ClientErrorCode, BizCodeRange } from "@ming/biz-common-net";
