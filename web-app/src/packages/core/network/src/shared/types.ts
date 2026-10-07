// src/packages/core/network/src/shared/types.ts
// 公共类型 —— restful 和 sse 模块共用

/** 公共请求配置字段 */
export interface CommonRequestConfig {
  timeout?: number;
  responseType?: "json" | "text" | "blob" | "arraybuffer";
  /** 用于取消（中止）正在进行的请求 */
  signal?: AbortSignal;
  [key: string]: unknown;
}

/**
 * 拦截器配置 - 支持数组形式，可以注入多个
 * T 在库内部会被使用（读属性、调用方法等），用 unknown 更安全；
 * 若 T 只是透传给用户、库内部不碰，则默认 any 更实用
 */
export interface InterceptorConfig<T = any> {
  onFulfilled?: (value: T) => T | Promise<T>;
  onRejected?: (error: any) => any;
}

export type InterceptorConfigCollection<T = any> =
  | InterceptorConfig<T>
  | InterceptorConfig<T>[];

/** 拦截器管理器接口 */
export interface InterceptorManager<T = any> {
  use(
    onFulfilled?: (value: T) => T | Promise<T>,
    onRejected?: (error: any) => any,
  ): number;
  eject(id: number): void;
}

/**
 * 【标准化请求】库无关的请求配置
 * 替换原 InternalAxiosRequestConfig，拦截器链中统一使用此结构
 * 底层从 axios 迁移到 fetch / undici 时，拦截器代码零改动
 */
export interface NormalizedRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  params?: Record<string, any>;
  data?: any;
  timeout?: number;
  responseType?: "json" | "text" | "blob" | "arraybuffer";
  signal?: AbortSignal;
}

/**
 * 【标准化响应】库无关的响应结构
 * 替换原 AxiosResponse
 */
export interface NormalizedResponse<T = any> {
  data: T;
  status: number;
  statusText: string;
  headers: Record<string, string>;
  config: NormalizedRequest;
}
