import type {
  HttpManager,
  HttpClient,
  RequestConfig,
} from "@ming/core-network";
import {
  BizCodeRange,
  ClientErrorCode,
  getBizCodeCategory,
} from "../error-code";
import type {
  BizApiResponse,
  BizRequestCallbacks,
  BizRequestConfig,
  BizResult,
  ErrDataResponse,
} from "../types";
import { ERROR_MESSAGES } from "../error-messages";
import {
  buildHttpCodeError,
  formatAxiosException,
} from "../shared/error-mapper";

const DEFAULT_TIMEOUT = 10000;

export class BizRestClient {
  constructor(private readonly httpManager: HttpManager) {}

  initConfig(
    config: BizRequestConfig | undefined,
  ): Omit<RequestConfig, "url" | "method"> | undefined {
    if (!config) return undefined;
    const { timeout, axiosConfig, ...rest } = config;
    return {
      ...rest,
      axiosConfig: {
        ...(timeout !== undefined ? { timeout } : {}),
        ...axiosConfig,
      },
    };
  }

  private async requestWrap<T = any, F = any>(
    requestPromise: Promise<{ httpCode: number; data?: BizApiResponse<T> }>,
    callbacks?: BizRequestCallbacks<T, F>,
  ): Promise<BizResult<T, F>> {
    const { onSuccess, onFailed, onFinally } = callbacks || {};
    let errRes: ErrDataResponse<F> | null = null;
    let successRes: BizApiResponse<T> | null = null;

    try {
      const { httpCode, data: bizBody } = await requestPromise;
      if (httpCode === 204) {
        successRes = {
          bizCode: BizCodeRange.SUCCESS_204,
          data: undefined as unknown as T,
        };
      } else if (httpCode !== 200) {
        errRes = buildHttpCodeError<F>(
          httpCode,
          bizBody as Record<string, any>,
        );
      } else if (!bizBody) {
        errRes = { bizCode: ClientErrorCode.HTTP_BODY_NULL_ERR };
      } else {
        const { bizCode, data } = bizBody;
        const category = getBizCodeCategory(bizCode);
        if (category === "success") successRes = { bizCode, data: data as T };
        else if (category === "fail") errRes = { bizCode, errData: data as F };
        else errRes = { bizCode: ClientErrorCode.HTTP_UNKNOWN_ERR };
      }
    } catch (error) {
      errRes = formatAxiosException<F>(error);
    }

    if (errRes) {
      try {
        onFailed?.(errRes);
      } catch (error) {
        console.error("[BizRestClient] onFailed callback error:", error);
      }
    } else if (successRes) {
      try {
        onSuccess?.(successRes);
      } catch (error) {
        console.error("[BizRestClient] onSuccess callback error:", error);
      }
    }

    try {
      onFinally?.();
    } catch (error) {
      console.error("[BizRestClient] onFinally callback error:", error);
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
      this.httpManager.get<BizApiResponse<T>>(url, this.initConfig(cfg)),
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
      this.httpManager.post<BizApiResponse<T>>(url, data, this.initConfig(cfg)),
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
      this.httpManager.put<BizApiResponse<T>>(url, data, this.initConfig(cfg)),
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
      this.httpManager.delete<BizApiResponse<T>>(url, this.initConfig(cfg)),
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
      this.httpManager.patch<BizApiResponse<T>>(
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
