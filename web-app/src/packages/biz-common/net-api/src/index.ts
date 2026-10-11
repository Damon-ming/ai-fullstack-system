// src/packages/biz-common/net-api/index.ts

export { initNetApi } from "./init";
export { netClient } from "./net-client";

// 内部提供者 setter —— bootstrap 注入 store 回调
export {
  setDebugGetter,
  setEncryptionSessionGetter,
  setTokenGetter,
} from "@ming/biz-common-net";
export type { INetClient } from "@ming/biz-common-net"; // re-export 接口

// 网络层类型继续从这里导出（这一层本来就是类型门面）
export type {
  BizApiSuccessResponse,
  BizApiErrorResponse,
  BizResult,
  BaseRequest,
  BizRequestConfig,
  BizRequestCallbacks,
  EncryptionSession,
  SseStreamOptions,
  SseStreamCallbacks,
  SseFinalState,
  SseStreamStatus,
} from "@ming/biz-common-net";
// SseRequestOptions 来自 core-network，需要单独导出
export type { SseRequestOptions } from "@ming/core-network";

// 加密 & 签名协议版本
export {
  ENCRYPTION_VERSION,
  SIGNATURE_VERSION,
  SYSTEM_VERSION,
} from "@ming/biz-common-net";

// 错误码 —— 与后端 error_codes.py / server_error.py 对齐
export {
  ErrorCode,
  ClientErrorCode,
  ServerSubSystem,
  System,
  SUCCESS,
  FAILURE,
  isSuccess,
  isFailure,
  isServerCode,
  getServerCodeCategory,
  getServerSafeMessage,
  getErrorMessage,
} from "@ming/biz-common-net";

// 兼容旧名（过渡期保留）
export { BizCodeRange, getBizCodeCategory } from "@ming/biz-common-net";
