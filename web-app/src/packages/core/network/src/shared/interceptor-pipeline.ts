// web-app/src/packages/core/network/src/shared/interceptor-pipeline.ts
// type: 类型擦除
import type {
  HttpClientConfig,
  InterceptorConfig,
  NormalizedRequest,
  NormalizedResponse,
} from "../types";

type RequestInterceptor = InterceptorConfig<NormalizedRequest>;
type ResponseInterceptor = InterceptorConfig<NormalizedResponse>;
type InterceptorConfigOptions = NonNullable<HttpClientConfig["interceptors"]>;

function asArray<T>(value?: T | T[]): T[] {
  return value ? (Array.isArray(value) ? value : [value]) : [];
}

/** Shared interceptor execution for REST requests and SSE request setup. */
export class InterceptorPipeline {
  private requestInterceptors: RequestInterceptor[];
  private responseInterceptors: ResponseInterceptor[];

  constructor(config?: HttpClientConfig["interceptors"]) {
    this.requestInterceptors = asArray(config?.request);
    this.responseInterceptors = asArray(config?.response);
  }

  addRequestInterceptor(
    interceptor: RequestInterceptor | RequestInterceptor[],
  ): () => void {
    const list = asArray(interceptor);
    this.requestInterceptors.push(...list);
    return () => {
      this.requestInterceptors = this.requestInterceptors.filter(
        (item) => !list.includes(item),
      );
    };
  }

  addResponseInterceptor(
    interceptor: ResponseInterceptor | ResponseInterceptor[],
  ): () => void {
    const list = asArray(interceptor);
    this.responseInterceptors.push(...list);
    return () => {
      this.responseInterceptors = this.responseInterceptors.filter(
        (item) => !list.includes(item),
      );
    };
  }

  async runRequest(
    value: NormalizedRequest,
    single?: InterceptorConfigOptions["request"],
  ): Promise<NormalizedRequest> {
    // let 声明一个变量
    let current = value;
    // 就是把两个数组"拼接"成一个新数组，而且是立即完成的（马上得到结果）。
    // 先遍历全局+单词拦截
    for (const interceptor of [
      ...this.requestInterceptors,
      ...asArray(single),
    ]) {
      try {
        if (interceptor.onFulfilled)
          current = await interceptor.onFulfilled(current);
      } catch (error) {
        await interceptor.onRejected?.(error);
        throw error;
      }
    }
    return current;
  }

  async runResponse(
    value: NormalizedResponse,
    single?: InterceptorConfigOptions["response"],
  ): Promise<NormalizedResponse> {
    let current = value;
    for (const interceptor of [
      ...this.responseInterceptors,
      ...asArray(single),
    ]) {
      try {
        if (interceptor.onFulfilled)
          current = await interceptor.onFulfilled(current);
      } catch (error) {
        await interceptor.onRejected?.(error);
        throw error;
      }
    }
    return current;
  }

  async runRejected(
    error: unknown,
    single?: InterceptorConfigOptions["response"],
  ): Promise<unknown> {
    let current = error;
    for (const interceptor of [
      ...this.responseInterceptors,
      ...asArray(single),
    ]) {
      if (!interceptor.onRejected) continue;
      try {
        current = await interceptor.onRejected(current);
      } catch (nextError) {
        current = nextError;
      }
    }
    return current;
  }

  getConfig(): HttpClientConfig["interceptors"] | undefined {
    if (!this.requestInterceptors.length && !this.responseInterceptors.length)
      return undefined;
    return {
      request: this.requestInterceptors.length
        ? [...this.requestInterceptors]
        : undefined,
      response: this.responseInterceptors.length
        ? [...this.responseInterceptors]
        : undefined,
    };
  }
}
