// src/packages/biz-common/net/src/interface.ts
import {
  BizRequestCallbacks,
  BizRequestConfig,
  BizResult,
} from "./restful/types";
import {
  SseFinalState,
  SseStreamCallbacks,
  SseStreamOptions,
} from "./sse/types";

export interface INetClient {
  get<T = any, F = any>(
    url: string,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  post<T = any, F = any>(
    url: string,
    data?: any,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  post<T = any, F = any>(
    url: string,
    data?: any,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;

  put<T = any, F = any>(
    url: string,
    data?: any,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  put<T = any, F = any>(
    url: string,
    data?: any,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;

  delete<T = any, F = any>(
    url: string,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  delete<T = any, F = any>(
    url: string,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;

  patch<T = any, F = any>(
    url: string,
    data?: any,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  patch<T = any, F = any>(
    url: string,
    data?: any,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;

  sseStream<T = any>(
    url: string,
    body: unknown,
    callbacks?: SseStreamCallbacks<T>,
    opts?: SseStreamOptions<T>,
  ): Promise<SseFinalState>;
}
