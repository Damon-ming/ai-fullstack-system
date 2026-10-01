// src/packages/biz-common/net/src/restful/types.ts
// RESTful 业务请求相关类型 —— 仅 RESTful 模块使用

import type { RequestConfig } from "@ming/core-network";
import type { BizApiSuccessResponse, BizApiErrorResponse } from "../shared/types";

/**
 * 单次业务请求配置 (BizRequestConfig)
 * 复用 core 的 RequestConfig (剔除 url 和 method)，并补充/覆盖业务特有配置
 */
export type BizRequestConfig = Omit<RequestConfig, "url" | "method"> & {
  /** 单次请求超时时间（单位：毫秒） */
  timeout?: number;
};

/** 请求回调集合 */
export interface BizRequestCallbacks<T = any, F = any> {
  onSuccess?: (res: BizApiSuccessResponse<T>) => void;
  onFailed?: (error: BizApiErrorResponse<F>) => void;
  onFinally?: () => void;
}

/**
 * 元组返回格式 [BizApiErrorResponse | null, BizApiSuccessResponse | null]
 * 失败：[BizApiErrorResponse, null]
 * 成功：[null, BizApiSuccessResponse]
 */
export type BizResult<T = any, F = any> = [
  BizApiErrorResponse<F> | null,
  BizApiSuccessResponse<T> | null,
];
