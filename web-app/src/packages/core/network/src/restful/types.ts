// src/packages/core/network/src/restful/types.ts
// RESTful 请求/响应相关类型 —— 仅 restful 模块使用

import type {
  CommonRequestConfig,
  InterceptorConfig,
  NormalizedRequest,
  NormalizedResponse,
} from "../shared/types";

/** 单次请求配置（接口维度） */
export interface RequestConfig {
  url: string;
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  params?: Record<string, any>;
  data?: any;
  headers?: Record<string, string | number | boolean | null | undefined>;
  axiosConfig?: CommonRequestConfig;
  interceptors?: {
    request?:
      | InterceptorConfig<NormalizedRequest>
      | InterceptorConfig<NormalizedRequest>[];
    response?:
      | InterceptorConfig<NormalizedResponse>
      | InterceptorConfig<NormalizedResponse>[];
  };
}

/** 客户端实例配置（实例维度） */
export interface HttpClientConfig {
  baseURL: string;
  headers?: Record<string, string | number | boolean | null | undefined>;
  axiosConfig?: CommonRequestConfig;
  interceptors?: {
    request?:
      | InterceptorConfig<NormalizedRequest>
      | InterceptorConfig<NormalizedRequest>[];
    response?:
      | InterceptorConfig<NormalizedResponse>
      | InterceptorConfig<NormalizedResponse>[];
  };
}

/** HTTP  ApiResponse（HTTP 壳） */
export interface ApiResponse<T = unknown> {
  code: number; // HTTP 状态码
  data: T;
}
