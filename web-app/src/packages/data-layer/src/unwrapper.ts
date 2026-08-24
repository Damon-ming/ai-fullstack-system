// src/packages/data-layer/src/unwrapper.ts
import type { BizApiResponse, ErrDataResponse, BizResult } from '@ming/biz-common-net-api'
import type { DataApiResponse, DataLayerError } from './types'

/**
 * 核心解包纯函数：将网络层返回的 [err, res] 元组转换为标准的 Standard Promise
 * - 成功：Resolve 完整的 BizApiResponse<T>
 * - 失败：Reject 完整的 ErrDataResponse<F>（供 TanStack Query 捕获并进入 isError 状态）
 */
export async function unwrapBizResult<T = any, F = any>(
  requestPromise: Promise<BizResult<T, F>>
): Promise<DataApiResponse<T>> {
  const [err, res] = await requestPromise

  if (err) {
    // 抛出错误，促使 TanStack Query 状态变为 isError，透传完整 ErrDataResponse
    return Promise.reject(err as DataLayerError<F>)
  }

  if (res) {
    // 成功，透传完整的 BizApiResponse
    return { bizCode: res.bizCode, data: res.data }
  }

  // 兜底防御
  return Promise.reject({
    bizCode: -1,
    clientErrData: { message: 'Unknown data layer error: Both res and err are null' }
  } as DataLayerError<F>)
}
