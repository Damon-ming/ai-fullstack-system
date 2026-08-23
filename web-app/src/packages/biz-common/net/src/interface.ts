import { BizRequestCallbacks, BizRequestConfig, BizResult } from "./types";

// src/packages/biz-common/net/src/interface.ts
export interface INetClient {
  get<T = any, F = any>(
    url: string,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  // ... 其余方法签名，和现在 interface.ts 一样
}
