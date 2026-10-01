import type { HttpManager } from "@ming/core-network";
import type {
  BizHttpClientConfig,
  ErrDataResponse,
  SseFinalState,
  SseGlobalMessageInterceptor,
  SseResponseHeadersInterceptor,
  SseStreamCallbacks,
  SseStreamStatus,
  SseStreamOptions,
} from "../types";
import { ClientErrorCode } from "../error-code";
import { buildHttpCodeError, formatSseException } from "../shared/error-mapper";

export class BizSseClient {
  private responseHeadersInterceptors: SseResponseHeadersInterceptor[] = [];
  private messageInterceptors: SseGlobalMessageInterceptor[] = [];

  constructor(private readonly httpManager: HttpManager) {}

  configure(
    // Pick<...> 是 TypeScript 的 工具类型
    // 从 BizHttpClientConfig 这个类型中，只挑选 sseResponseHeadersInterceptors 和 sseMessageInterceptors 这两个属性，组成一个新的类型
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
    const { onMessage, onError, onComplete } = callbacks;
    const {
      // false | ((raw: string) => T)，	把原始字符串转成 payload。默认 JSON.parse
      parse,
      validateMessage,
      messageInterceptors,
      onResponseHeaders,
      ...transportOptions
    } = opts;
    const localInterceptors = messageInterceptors
      ? Array.isArray(messageInterceptors)
        ? messageInterceptors
        : [messageInterceptors]
      : [];

    const safeOnMessage = (
      payload: T,
      meta?: { event?: string; id?: string },
    ) => {
      try {
        onMessage?.(payload, meta);
      } catch (error) {
        console.error("[BizSseClient] onMessage callback error:", error);
      }
    };
    const safeOnError = (error: ErrDataResponse) => {
      try {
        onError?.(error);
      } catch (callbackError) {
        console.error("[BizSseClient] onError callback error:", callbackError);
      }
    };
    const safeOnMessageError = (error: unknown, rawPayload: string) => {
      try {
        callbacks.onMessageError?.(error, rawPayload);
      } catch (callbackError) {
        console.warn(
          "[BizSseClient] onMessageError callback error:",
          callbackError,
        );
      }
    };
    const safeOnComplete = () => {
      try {
        onComplete?.();
      } catch (error) {
        console.error("[BizSseClient] onComplete callback error:", error);
      }
    };
    const emitStatus = (status: SseStreamStatus) => {
      try {
        callbacks.onStatus?.(status);
      } catch (error) {
        console.warn("[BizSseClient] onStatus callback error:", error);
      }
    };

    try {
      const response = await this.httpManager.sse(url, body, transportOptions);
      for (const interceptor of this.responseHeadersInterceptors) {
        try {
          await interceptor.onFulfilled?.(response);
        } catch (error) {
          try {
            await interceptor.onRejected?.(error);
          } catch {
            // Header interceptor errors must not terminate the stream.
          }
        }
      }
      try {
        await onResponseHeaders?.(response);
      } catch (error) {
        console.warn("[BizSseClient] onResponseHeaders error:", error);
      }

      if (!response.ok) {
        // response.text() 返回 Promise
        // catch(() => "")：出错时返回空字符串 ""，不让异常抛出去
        const text = await response.text().catch(() => "");
        const error = buildHttpCodeError(
          response.status,
          text ? { message: text, rawBody: text } : undefined,
        );
        emitStatus("transport-error");
        safeOnError(error);
        return { status: "error", error };
      }

      const reader = response.body?.getReader();
      if (!reader) {
        const error: ErrDataResponse = {
          bizCode: ClientErrorCode.HTTP_UNKNOWN_CLIENT_ERR,
          clientErrData: { message: "ReadableStream reader is not available" },
        };
        emitStatus("transport-error");
        safeOnError(error);
        return { status: "error", error };
      }

      emitStatus("connected");

      // 二进制字节（Uint8Array）解码成字符串。
      const decoder = new TextDecoder("utf-8");
      // 这是标准的 SSE 协议解析，遵循 data: / event: / id: / :（注释/心跳）四类行。
      let buffer = "";
      let eventData = "";
      let eventType = "message";
      let lastEventId = "";

      const dispatch = async () => {
        if (!eventData) return;
        emitStatus("message");
        // CRLF	CR + LF	回车+换行	\r\n
        const rawPayload = eventData.replace(/\n$/, "");
        const meta = { event: eventType, id: lastEventId };
        try {
          let payload: T =
            parse === false
              ? (rawPayload as T)
              : // JSON.parse 是 JavaScript 内置函数，把 JSON 字符串 转成 JS 对象/值。
                (parse ?? JSON.parse)(rawPayload);
          // 它比较两个值时，同时要求类型和值都相同，才返回 true
          if ((payload as { event?: string } | null)?.event === "error") {
            emitStatus("business-error");
          }
          if (validateMessage) {
            const result = validateMessage(payload);
            if (result.isError && result.error) {
              emitStatus("business-error");
              safeOnError(result.error);
              return;
            }
          }
          for (const interceptor of [
            ...this.messageInterceptors,
            ...localInterceptors,
          ]) {
            try {
              if (interceptor.onFulfilled)
                payload = await interceptor.onFulfilled(payload, meta);
            } catch (error) {
              const handled = await interceptor.onRejected?.(error);
              if (handled === false) return;
              throw error;
            }
          }
          safeOnMessage(payload, meta);
        } catch (error) {
          emitStatus("parse-error");
          safeOnMessageError(error, rawPayload);
          console.warn("[BizSseClient] message process failed", {
            raw: rawPayload,
            error,
          });
        } finally {
          eventData = "";
          eventType = "message";
          lastEventId = "";
        }
      };

      const processLine = (line: string) => {
        if (line.startsWith(":")) {
          emitStatus("heartbeat");
          return;
        }
        if (line.startsWith("data:"))
          eventData += `${line.slice(5).trimStart()}\n`;
        else if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("id:")) lastEventId = line.slice(3).trim();
      };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          // 把二进制 value 解码为字符串。
          // stream: true 表示这不是最后一块：如果末尾正好截断了一个多字节字符（如中文一个字占 3 字节），先缓存起来不输出，等下一块拼齐再解码。
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          // Array.prototype.pop() 是数组方法：删除并返回数组的最后一个元素。
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            // SSE servers commonly use CRLF. After splitting on LF, the
            // blank separator is represented as "\r", not "".
            const normalizedLine = line.endsWith("\r")
              ? line.slice(0, -1)
              : line;
            if (normalizedLine === "") await dispatch();
            else processLine(normalizedLine);
          }
        }
        // Flush a possible multi-byte UTF-8 sequence held by TextDecoder.
        buffer += decoder.decode();
        if (buffer) {
          for (const line of buffer.split("\n")) {
            const normalizedLine = line.endsWith("\r")
              ? line.slice(0, -1)
              : line;
            if (normalizedLine === "") await dispatch();
            else processLine(normalizedLine);
          }
          // 不遇到空行，就只累积（processLine 往 eventData 里加）。
          // 一遇到空行，才把累积的内容打包派发出去。
          await dispatch();
        }
        emitStatus("complete");
        safeOnComplete();
        return { status: "complete" };
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      const mapped = formatSseException(error);
      emitStatus(
        mapped.bizCode === ClientErrorCode.CONFIG_CANCEL
          ? "aborted"
          : "transport-error",
      );
      safeOnError(mapped);
      return { status: "error", error: mapped };
    }
  }
}
