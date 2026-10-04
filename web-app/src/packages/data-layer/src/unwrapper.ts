// src/packages/data-layer/src/unwrapper.ts
import type { BizResult } from "@ming/biz-common-net-api";
import type { DataApiResponse, DataLayerError } from "./types";

/**
 * 核心解包纯函数：将网络层返回的 [err, res] 元组转换为标准的 Standard Promise
 * - 成功：Resolve 完整的 BizApiSuccessResponse<T>
 * - 失败：Reject 完整的 BizApiErrorResponse<F>（供 TanStack Query 捕获并进入 isError 状态）
 *
 * async 函数有一个特性：函数体里 throw 出去的值，会自动转成 rejected Promise。
 */
export async function unwrapBizResult<T = any, F = any>(
  requestPromise: Promise<BizResult<T, F>>,
): Promise<DataApiResponse<T>> {
  const [err, res] = await requestPromise;

  if (err) {
    // throw 自动变为 rejected Promise，促使 TanStack Query 进入 isError 状态
    // eslint-disable-next-line @typescript-eslint/no-throw-literal -- BizApiErrorResponse 是结构化业务错误对象，非 Error 实例
    throw err as DataLayerError<F>;
  }

  if (res) {
    // 成功，透传完整的 BizApiSuccessResponse
    return { code: res.code, data: res.data };
  }

  // 兜底防御
  // eslint-disable-next-line @typescript-eslint/no-throw-literal -- 结构化业务错误对象，非 Error 实例
  throw {
    code: -1,
    clientData: {
      message: "CLIENT:Unknown data layer error: Both res and err are null",
    },
  } as DataLayerError<F>;
}
