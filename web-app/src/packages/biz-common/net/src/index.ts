// src/packages/biz-common/net/src/index.ts
export { BizHttp } from "./biz-http";
export { SYSTEM_VERSION } from "./version";
export { createCommonHeaderInterceptor } from "./header/common-header-interceptor";
export { createEncryptionInterceptors } from "./encryption/encryption-interceptor";
export { ENCRYPTION_VERSION, SIGNATURE_VERSION } from "./encryption/encryption-types";
export type {
  EncryptionSession,
} from "./encryption/encryption-types";
export { encryptJson, decryptPayload } from "./encryption/encryption-crypto";
export { computeSignature } from "./encryption/signature";
export { generateNonce } from "@ming/core-encryption";
export type { EncryptedResult } from "./encryption/encryption-types";
export * from "./shared/types";
export * from "./sse/types";
export * from "./restful/types";

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
  getCategory,
  getSystem,
  getBusiness,
  getDetail,
} from "./error-code";

// 错误消息 & 辅助函数
export {
  ERROR_MESSAGES,
  HTTP_STATUS_MESSAGES,
  getHttpStatusMessage,
  getServerSafeMessage,
  getErrorMessage,
} from "./error-messages";

// 错误映射器
export {
  buildHttpCodeError,
  formatAxiosException,
  formatSseException,
  buildSseErrorPayload,
} from "./shared/error-mapper";

// 兼容旧名（过渡期保留）
export { BizCodeRange, getBizCodeCategory } from "./error-code";

export type { INetClient } from "./interface";
