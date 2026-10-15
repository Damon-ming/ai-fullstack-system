// web-app/src/packages/biz-common/net/src/restful/biz-rest-client.ts
import type { HttpManager, RequestConfig } from "@ming/core-network";
import { createLogger } from "@ming/core-log";
import { ErrorCode, isSuccess } from "../error-code";
import type {
  BizApiSuccessResponse,
  BizApiErrorResponse,
} from "../shared/types";
import type { BizRequestCallbacks, BizRequestConfig, BizResult } from "./types";
import {
  buildHttpCodeError,
  formatAxiosException,
} from "../shared/error-mapper";
import { getServerSafeMessage } from "../error-messages";

const log = createLogger("net/restful");
const DEFAULT_TIMEOUT = 10000;

export class BizRestClient {
  constructor(private readonly httpManager: HttpManager) {}

  initConfig(
    config: BizRequestConfig | undefined,
  ): Omit<RequestConfig, "url" | "method"> | undefined {
    if (!config) return undefined;
    const { timeout, signal, axiosConfig, ...rest } = config;
    return {
      ...rest,
      axiosConfig: {
        ...(timeout !== undefined ? { timeout } : {}),
        ...(signal ? { signal } : {}),
        ...axiosConfig,
      },
    };
  }

  private async requestWrap<T = any, F = any>(
    requestPromise: Promise<{ code: number; data?: BizApiSuccessResponse<T> }>,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>> {
    const { onSuccess, onFailed, onFinally } = callbacks || {};
    let errRes: BizApiErrorResponse<F> | null = null;
    let successRes: BizApiSuccessResponse<T> | null = null;

    try {
      const { code: httpCode, data: bizBody } = await requestPromise;

      // HTTP 非 2xx → 走错误构造（内部判断服务端是否有结构化 body）
      if (httpCode < 200 || httpCode >= 300) {
        errRes = buildHttpCodeError<F>(
          httpCode,
          bizBody as Record<string, any>,
        );
      }
      // HTTP 2xx + 有 body → 拆包业务码
      else if (bizBody && typeof bizBody.code === "number") {
        const { code, data } = bizBody;
        if (isSuccess(code)) {
          successRes = { code, data: data as T };
        } else {
          // 服务端业务失败码 → 确保 data.error_msg 有值
          // 优先级：data.error_msg（服务端原始描述）> getServerSafeMessage（子系统兜底文案）
          const errorMsg =
            data &&
            typeof data === "object" &&
            typeof (data as Record<string, unknown>).error_msg === "string"
              ? ((data as Record<string, unknown>).error_msg as string)
              : getServerSafeMessage(code);
          errRes = {
            code,
            data: {
              ...(data as Record<string, unknown>),
              error_msg: errorMsg,
            } as F,
          };
        }
      }
      // HTTP 204 或 2xx + 空 body → 成功（无业务数据）
      else {
        successRes = {
          code: ErrorCode.OK,
          data: undefined as unknown as T,
        };
      }
    } catch (error) {
      errRes = formatAxiosException<F>(error);
    }

    if (errRes) {
      try {
        onFailed?.(errRes);
      } catch (error) {
        log.error("onFailed callback error", error);
      }
    } else if (successRes) {
      try {
        onSuccess?.(successRes);
      } catch (error) {
        log.error("onSuccess callback error", error);
      }
    }

    try {
      onFinally?.();
    } catch (error) {
      log.error("onFinally callback error", error);
    }
    return [errRes, successRes];
  }

  private isCallbacks<T, F>(value: any): value is BizRequestCallbacks<T, F> {
    return Boolean(
      value &&
      (typeof value.onSuccess === "function" ||
        typeof value.onFailed === "function" ||
        typeof value.onFinally === "function"),
    );
  }

  // 核心：因为调用者可能传 (url, config) 或 (url, callbacks) 或 (url, config, callbacks)，所以需要"猜"第二个参数到底是配置还是回调。
  private parseArgs<T, F>(arg2?: any, arg3?: any) {
    return {
      cfg: this.isCallbacks<T, F>(arg2)
        ? undefined
        : (arg2 as BizRequestConfig | undefined),
      callbacks: this.isCallbacks<T, F>(arg2)
        ? arg2
        : (arg3 as BizRequestCallbacks<T, F> | undefined),
    };
  }

  get<T = any, F = any>(
    url: string,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  get<T = any, F = any>(
    url: string,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  get<T = any, F = any>(
    url: string,
    arg2?: any,
    arg3?: any,
  ): Promise<BizResult<T, F>> {
    const { cfg, callbacks } = this.parseArgs<T, F>(arg2, arg3);
    return this.requestWrap(
      this.httpManager.get<BizApiSuccessResponse<T>>(url, this.initConfig(cfg)),
      callbacks,
    );
  }

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
  post<T = any, F = any>(
    url: string,
    data?: any,
    arg3?: any,
    arg4?: any,
  ): Promise<BizResult<T, F>> {
    const { cfg, callbacks } = this.parseArgs<T, F>(arg3, arg4);
    return this.requestWrap(
      this.httpManager.post<BizApiSuccessResponse<T>>(
        url,
        data,
        this.initConfig(cfg),
      ),
      callbacks,
    );
  }

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
  put<T = any, F = any>(
    url: string,
    data?: any,
    arg3?: any,
    arg4?: any,
  ): Promise<BizResult<T, F>> {
    const { cfg, callbacks } = this.parseArgs<T, F>(arg3, arg4);
    return this.requestWrap(
      this.httpManager.put<BizApiSuccessResponse<T>>(
        url,
        data,
        this.initConfig(cfg),
      ),
      callbacks,
    );
  }

  delete<T = any, F = any>(
    url: string,
    cfg?: BizRequestConfig,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  delete<T = any, F = any>(
    url: string,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>>;
  delete<T = any, F = any>(
    url: string,
    arg2?: any,
    arg3?: any,
  ): Promise<BizResult<T, F>> {
    const { cfg, callbacks } = this.parseArgs<T, F>(arg2, arg3);
    return this.requestWrap(
      this.httpManager.delete<BizApiSuccessResponse<T>>(
        url,
        this.initConfig(cfg),
      ),
      callbacks,
    );
  }

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
  patch<T = any, F = any>(
    url: string,
    data?: any,
    arg3?: any,
    arg4?: any,
  ): Promise<BizResult<T, F>> {
    const { cfg, callbacks } = this.parseArgs<T, F>(arg3, arg4);
    return this.requestWrap(
      this.httpManager.patch<BizApiSuccessResponse<T>>(
        url,
        data,
        this.initConfig(cfg),
      ),
      callbacks,
    );
  }

  static getDefaultTimeout(): number {
    return DEFAULT_TIMEOUT;
  }
}
