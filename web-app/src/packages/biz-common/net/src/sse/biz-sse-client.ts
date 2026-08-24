import type { HttpManager } from "@ming/core-network";
import type {
  BizHttpClientConfig,
  ErrDataResponse,
  SseFinalState,
  SseGlobalMessageInterceptor,
  SseResponseHeadersInterceptor,
  SseStreamCallbacks,
  SseStreamOptions,
} from "../types";
import { ClientErrorCode } from "../error-code";
import { buildHttpCodeError, formatSseException } from "../shared/error-mapper";

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

  async stream<T = any>(
    url: string,
    body: unknown,
    callbacks: SseStreamCallbacks<T> = {},
    opts: SseStreamOptions<T> = {},
  ): Promise<SseFinalState> {
    const { onMessage, onError, onComplete } = callbacks;
    const {
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
    const safeOnComplete = () => {
      try {
        onComplete?.();
      } catch (error) {
        console.error("[BizSseClient] onComplete callback error:", error);
      }
    };

    try {
      const response = await this.httpManager.sse(url, body, transportOptions);
      for (const interceptor of this.responseHeadersInterceptors) {
        try {
          await interceptor.onFulfilled?.(response);
        } catch (error) {
          try {
            interceptor.onRejected?.(error);
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
        const text = await response.text().catch(() => "");
        const error = buildHttpCodeError(
          response.status,
          text ? { message: text, rawBody: text } : undefined,
        );
        safeOnError(error);
        return { status: "error", error };
      }

      const reader = response.body?.getReader();
      if (!reader) {
        const error: ErrDataResponse = {
          bizCode: ClientErrorCode.HTTP_UNKNOWN_CLIENT_ERR,
          clientErrData: { message: "ReadableStream reader is not available" },
        };
        safeOnError(error);
        return { status: "error", error };
      }

      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let eventData = "";
      let eventType = "message";
      let lastEventId = "";

      const dispatch = async () => {
        if (!eventData) return;
        const rawPayload = eventData.replace(/\n$/, "");
        const meta = { event: eventType, id: lastEventId };
        try {
          let payload: T =
            parse === false
              ? (rawPayload as T)
              : (parse ?? JSON.parse)(rawPayload);
          if (validateMessage) {
            const result = validateMessage(payload);
            if (result.isError && result.error) {
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
              const handled = interceptor.onRejected?.(error);
              if (handled === false) return;
              throw error;
            }
          }
          safeOnMessage(payload, meta);
        } catch (error) {
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
        if (line.startsWith(":")) return;
        if (line.startsWith("data:"))
          eventData += `${line.slice(5).trimStart()}\n`;
        else if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("id:")) lastEventId = line.slice(3).trim();
      };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
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
          await dispatch();
        }
        safeOnComplete();
        return { status: "complete" };
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      const mapped = formatSseException(error);
      safeOnError(mapped);
      return { status: "error", error: mapped };
    }
  }

  request(
    url: string,
    body?: unknown,
    opts?: Parameters<HttpManager["sse"]>[2],
  ) {
    return this.httpManager.sse(url, body, opts);
  }
}
