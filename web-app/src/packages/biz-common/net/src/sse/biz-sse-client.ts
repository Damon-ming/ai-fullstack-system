// web-app/src/packages/biz-common/net/src/sse/biz-sse-client.ts
import type { HttpManager } from "@ming/core-network";
import type { BizHttpClientConfig, BizApiErrorResponse } from "../shared/types";
import type {
  SseFinalState,
  SseGlobalMessageInterceptor,
  SseMessageInterceptor,
  SseResponseHeadersInterceptor,
  SseStreamCallbacks,
  SseStreamStatus,
  SseStreamOptions,
} from "./types";
import { ClientErrorCode } from "../error-code";
import { buildHttpCodeError, formatSseException } from "../shared/error-mapper";
import { SseParser } from "./sse-parser";

export class BizSseClient {
  private responseHeadersInterceptors: SseResponseHeadersInterceptor[] = [];
  private messageInterceptors: SseGlobalMessageInterceptor[] = [];

  constructor(private readonly httpManager: HttpManager) {}

  configure(
    config: Pick<
      BizHttpClientConfig,
      "sseResponseHeadersInterceptors" | "sseMessageInterceptors"
    >,
  ) {
    this.responseHeadersInterceptors = config.sseResponseHeadersInterceptors
      ? Array.isArray(config.sseResponseHeadersInterceptors)
        ? config.sseResponseHeadersInterceptors
        : [config.sseResponseHeadersInterceptors]
      : [];
    this.messageInterceptors = config.sseMessageInterceptors
      ? Array.isArray(config.sseMessageInterceptors)
        ? config.sseMessageInterceptors
        : [config.sseMessageInterceptors]
      : [];
  }

  // 字段	含义	示例
  // data:	消息数据	data: {"a":1}
  // event:	事件类型	event: update
  // id:	事件 ID	id: 42
  // retry:	重连等待毫秒数	retry: 3000
  // : 开头	注释/心跳	: keep-alive
  // ← 空行 = 事件结束，派发
  // : 开头是注释，客户端不派发为消息
  // SSE 的响应体是纯文本，按行组织，遵循 W3C 规范。
  // SSE 用空行表示"一个事件结束"。

  // 服务器 ──chunk字节──► TextDecoder ──文本──► buffer(行缓冲)
  //                                             │
  //                                    split("\n") + pop()
  //                                             │
  //                                    完整行逐行处理
  //                                      ├─ ":" → 心跳
  //                                      ├─ "data:" → 累积 eventData
  //                                      ├─ "event:" → eventType
  //                                      ├─ "id:" → lastEventId
  //                                      └─ "" → dispatch()（空行派发）
  //                                                 │
  //                                                 ▼
  //                                    解析 → 校验 → 拦截器 → onMessage

  // 客户端发请求
  //     │
  //     ▼
  // 服务端: 200 OK + text/event-stream
  //     │
  //     ├─ : keep-alive              ← 心跳
  //     ├─ id:1 data:{start}         ← 开始
  //     ├─ : keep-alive
  //     ├─ id:2 data:{delta:"你"}    ← 逐字推
  //     ├─ id:3 data:{delta:"好"}
  //     ├─ id:4 data:{delta:"，"}
  //     ├─ id:5 data:{delta:"世界"}
  //     ├─ id:6 data:{end}           ← 结束
  //     │
  //     ▼
  // 服务端关闭连接（或保持）
  //     │
  //     ▼
  // 客户端: onMessage 每条触发一次
  //         最后 onComplete
  async stream<T = any>(
    url: string,
    body: unknown,
    callbacks: SseStreamCallbacks<T> = {},
    opts: SseStreamOptions<T> = {},
  ): Promise<SseFinalState> {
    const {
      parse,
      validateMessage,
      messageInterceptors,
      onResponseHeaders,
      ...transportOptions
    } = opts;
    const localInterceptors = this.normalizeInterceptors(messageInterceptors);

    try {
      // ── 1. 建立连接 ─────────────────────────────────────────
      const response = await this.httpManager.sse(url, body, transportOptions);
      await this.runHeaderInterceptors(response);
      await onResponseHeaders?.(response);

      if (!response.ok) {
        const text = await response.text().catch(() => "");
        const error = buildHttpCodeError(
          response.status,
          text ? { message: text, rawBody: text } : undefined,
        );
        this.emitStatus(callbacks, "transport-error");
        this.safeOnError(callbacks, error);
        return { status: "error", error };
      }

      const reader = response.body?.getReader();
      if (!reader) {
        const error: BizApiErrorResponse = {
          code: ClientErrorCode.CONFIG_ERR,
          clientData: { message: "ReadableStream reader is not available" },
        };
        this.emitStatus(callbacks, "transport-error");
        this.safeOnError(callbacks, error);
        return { status: "error", error };
      }

      // ── 2. SSE 协议解析（委托给 SseParser）─────────────────
      this.emitStatus(callbacks, "connected");
      const parser = new SseParser<T>(callbacks, {
        parse,
        validateMessage,
        globalInterceptors: this.messageInterceptors,
        localInterceptors,
      });
      return await parser.parse(reader);
    } catch (error) {
      const mapped = formatSseException(error);
      this.emitStatus(
        callbacks,
        mapped.code === ClientErrorCode.CONFIG_CANCEL ? "aborted" : "transport-error",
      );
      this.safeOnError(callbacks, mapped);
      return { status: "error", error: mapped };
    }
  }

  // ─── 私有辅助 ───────────────────────────────────────────────

  private normalizeInterceptors(
    messageInterceptors: SseStreamOptions<any>["messageInterceptors"],
  ): SseMessageInterceptor[] {
    if (!messageInterceptors) return [];
    return Array.isArray(messageInterceptors) ? messageInterceptors : [messageInterceptors];
  }

  private async runHeaderInterceptors(response: Response): Promise<void> {
    for (const interceptor of this.responseHeadersInterceptors) {
      try {
        const result = interceptor.onFulfilled?.(response);
        if (result) await Promise.resolve(result);
      } catch (error) {
        try {
          const handled = interceptor.onRejected?.(error);
          if (handled) await Promise.resolve(handled);
        } catch {
          // Header interceptor errors must not terminate the stream.
        }
      }
    }
  }

  private emitStatus(callbacks: SseStreamCallbacks, status: SseStreamStatus): void {
    try {
      callbacks.onStatus?.(status);
    } catch (error) {
      console.warn("[BizSseClient] onStatus callback error:", error);
    }
  }

  private safeOnError(callbacks: SseStreamCallbacks, error: BizApiErrorResponse): void {
    try {
      callbacks.onError?.(error);
    } catch (callbackError) {
      console.error("[BizSseClient] onError callback error:", callbackError);
    }
  }
}
