// src/packages/core/network/src/types.ts
// 保留必要字段，按场景拆分
// 公共：剔除冲突字段后的 axios 扩展配置，两处共用
// interface 想成一张表格模板 / 一份合同，用来描述一个对象的"形状"（结构）
export interface CommonRequestConfig {
  timeout?: number;
  // 控制跨域请求时是否携带凭据（Cookie、认证头等）
  withCredentials?: boolean;
  responseType?: "json" | "text" | "blob" | "arraybuffer";
  // 用于取消（中止）正在进行的请求
  signal?: AbortSignal;
  [key: string]: unknown;
}

// 单次请求配置（接口维度）
export interface RequestConfig {
  url: string;
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  params?: Record<string, any>;
  data?: any;
  headers?: Record<string, string | number | boolean | null | undefined>;
  axiosConfig?: CommonRequestConfig;
  //  新增单次请求拦截器
  interceptors?: {
    // InternalAxiosRequestConfig 是专门为请求拦截器设计的内部类型，而 AxiosRequestConfig 是你在创建请求时传入的通用配置类型
    // AxiosRequestConfig 中的 headers 通常允许是多种类型，比如 RawAxiosRequestHeaders & MethodsHeaders 的交叉类型，或 AxiosHeaders 对象。
    // 而 InternalAxiosRequestConfig 明确要求 headers 必须是 AxiosRequestHeaders 类型，且不再是可选属性
    request?:
      | InterceptorConfig<NormalizedRequest>
      | InterceptorConfig<NormalizedRequest>[];
    response?:
      | InterceptorConfig<NormalizedResponse>
      | InterceptorConfig<NormalizedResponse>[];
  };
}

// 客户端实例配置（实例维度）
export interface HttpClientConfig {
  baseURL: string;
  // null：主动置空，人为赋的"没有值"	undefined：未定义，还没赋值 / 不存在
  headers?: Record<string, string | number | boolean | null | undefined>;
  axiosConfig?: CommonRequestConfig; // 复用公共类型，不再重复写Omit
  interceptors?: {
    request?:
      | InterceptorConfig<NormalizedRequest>
      | InterceptorConfig<NormalizedRequest>[];
    response?:
      | InterceptorConfig<NormalizedResponse>
      | InterceptorConfig<NormalizedResponse>[];
  };
}

// 这个类型参数在库内部会被使用（读属性、调用方法等），那用 unknown 更安全
// 而如果 T 只是透传给用户、库内部不碰，那默认 any 更实用：
// 拦截器配置 - 支持数组形式，可以注入多个
export interface InterceptorConfig<T = any> {
  // T | Promise<T> 表示这个函数既可以返回同步值（T），也可以返回异步的 Promise（Promise<T>）
  // 是的！ => any 表示函数的返回值类型是 any
  onFulfilled?: (value: T) => T | Promise<T>;
  onRejected?: (error: any) => any;
}

export type InterceptorConfigCollection<T = any> =
  | InterceptorConfig<T>
  | InterceptorConfig<T>[];

// any 让你失去了 TypeScript 的所有保护，编译时不会报错，但运行时可能崩溃。
// unknown —— 安全的类型检查
export interface ApiResponse<T = unknown> {
  httpCode: number; // HTTP状态码
  data: T;
}

// 拦截器管理器接口
export interface InterceptorManager<T = any> {
  // use(...) —— 注册一个拦截器,返回值是一个数字，代表这个拦截器的唯一 id
  use(
    onFulfilled?: (value: T) => T | Promise<T>,
    onRejected?: (error: any) => any,
  ): number;
  // eject(id: number): void —— 移除拦截器
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
  withCredentials?: boolean;
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
