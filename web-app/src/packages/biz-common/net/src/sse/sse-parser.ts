// web-app/src/packages/biz-common/net/src/sse/sse-parser.ts
import { createLogger } from "@ming/core-log";
import type { BizApiErrorResponse } from "../shared/types";
import { getBizCodeCategory } from "../error-code";
import type {
  SseStreamCallbacks,
  SseStreamStatus,
  SseFinalState,
  SseMessageInterceptor,
} from "./types";

const log = createLogger("net/sse-parser");

/**
 * 默认业务校验：仅当 payload 含有 number 类型的 code 时，
 * 按 bizCode 范围判断成功/失败。无 code 的流式消息（如 chat delta）直接放行。
 */
function defaultValidateMessage<T>(payload: T): { isError: boolean; error?: BizApiErrorResponse } {
  if (payload && typeof payload === "object" && typeof (payload as any).code === "number") {
    const code = (payload as any).code as number;
    if (getBizCodeCategory(code) === "fail") {
      return {
        isError: true,
        error: { code, data: (payload as any).data },
      };
    }
  }
  return { isError: false };
}

interface SseParserOptions<T> {
  parse?: ((raw: string) => T) | false;
  validateMessage?: (payload: T) => {
    isError: boolean;
    error?: BizApiErrorResponse;
  };
  globalInterceptors?: SseMessageInterceptor[];
  localInterceptors?: SseMessageInterceptor[];
}

/**
 * SSE 协议解析器
 * 职责：从 ReadableStream 读取字节 → 按行解析 SSE 协议 → 派发事件/错误/完成
 *
 * 状态机：
 *   connected → (heartbeat | retry-updated | message | business-error | parse-error)* → complete
 *   connected → (business-error)* → error
 */
export class SseParser<T = any> {
  // SSE 协议状态（事件级，每条事件后重置）
  private eventData = "";
  private eventType = "message";
  // SSE 连接级状态（持续记忆，不重置）
  private lastEventId = "";
  private retryMs: number | undefined;
  // 流终止状态
  private hasError = false;
  private errorPayload: BizApiErrorResponse | undefined;
  private sentOnError = false;

  constructor(
    private readonly callbacks: SseStreamCallbacks<T>,
    private readonly opts: SseParserOptions<T>,
  ) {}

  get retry(): number | undefined {
    return this.retryMs;
  }

  /**
   * 解析流的入口：读取所有 chunk，按 SSE 协议行处理，遇到终止事件提前退出
   */
  async parse(
    reader: ReadableStreamDefaultReader<Uint8Array>,
  ): Promise<SseFinalState> {
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // stream: true — 多字节字符截断时缓存，等下一块拼齐再解码
        buffer += decoder.decode(value, { stream: true });
        // 保留最后一个不完整的行到下一次 chunk
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        if (await this.processLines(lines)) break; // hasError → 终止
      }

      if (!this.hasError) {
        // Flush 可能残留的多字节序列
        buffer += decoder.decode();
        if (buffer) {
          // 最后一块没有尾随 \n，直接作为一行处理
          const line = buffer.endsWith("\r") ? buffer.slice(0, -1) : buffer;
          if (line) this.processLine(line);
        }
        // 兜底：无尾随空行时派发最后累积的事件
        await this.dispatch();
      }

      if (!this.hasError) {
        this.emitStatus("complete");
        this.safeOnComplete();
        return { status: "complete" };
      }
      return { status: "error", error: this.errorPayload ?? { code: 300003 } };
    } finally {
      reader.releaseLock();
    }
  }

  /**
   * 处理一组完整行（不含最后一行不完整的）
   * @returns true 表示遇到终止事件，应停止读流
   */
  private async processLines(lines: string[]): Promise<boolean> {
    for (const line of lines) {
      // SSE servers commonly use CRLF. After splitting on LF, the
      // blank separator is represented as "\r", not "".
      const normalizedLine = line.endsWith("\r") ? line.slice(0, -1) : line;
      if (normalizedLine === "") {
        await this.dispatch();
      } else {
        this.processLine(normalizedLine);
      }
      if (this.hasError) return true;
    }
    return false;
  }

  /**
   * 解析单行 SSE 协议字段
   * 遵循 W3C 规范：:（注释/心跳）/ data: / event: / id: / retry:
   */
  private processLine(line: string): void {
    if (line.startsWith(":")) {
      this.emitStatus("heartbeat");
      return;
    }
    if (line.startsWith("data:")) {
      this.eventData += `${line.slice(5).trimStart()}\n`;
    } else if (line.startsWith("event:")) {
      this.eventType = line.slice(6).trim();
    } else if (line.startsWith("id:")) {
      this.lastEventId = line.slice(3).trim();
    } else if (line.startsWith("retry:")) {
      // retry: 连接级配置，通知客户端断线重连的等待毫秒数
      const val = line.slice(6).trim();
      const parsed = Number.parseInt(val, 10);
      if (!Number.isNaN(parsed)) {
        this.retryMs = parsed;
        this.emitStatus("retry-updated");
      }
    }
  }

  /**
   * 派发一个完整事件：解析 payload → 校验 → 拦截器 → onMessage
   * error 事件是终止通知，不往下走 onMessage
   */
  private async dispatch(): Promise<void> {
    // error 事件允许无 data:；其他事件空 payload 跳过
    if (!this.eventData && this.eventType !== "error") return;

    const rawPayload = this.eventData ? this.eventData.replace(/\n$/, "") : "";
    const meta = {
      event: this.eventType,
      id: this.lastEventId,
      retry: this.retryMs,
    };

    try {
      const payload = this.parsePayload(rawPayload);

      // 服务端通过 SSE event: error 通知异常终止
      if (this.eventType === "error" && !this.hasError) {
        this.hasError = true;
        if (!this.sentOnError) {
          this.emitStatus("business-error");
          this.errorPayload = {
            code: (payload as { code?: number })?.code ?? 300003,
            data: (payload as { data?: unknown })?.data,
          };
          this.safeOnError(this.errorPayload);
          this.sentOnError = true;
        }
        return; // error 终止事件不走 onMessage / 拦截器
      }

      // 业务层校验：优先用上层自定义，否则用内置默认（基于 bizCode 范围）
      const validator = this.opts.validateMessage ?? defaultValidateMessage;
      const result = validator(payload);
      if (result.isError && result.error) {
        if (!this.sentOnError) {
          this.emitStatus("business-error");
          this.safeOnError(result.error);
          this.sentOnError = true;
        }
        return;
      }

      // 拦截器链
      let processedPayload = payload;
      for (const interceptor of [
        ...(this.opts.globalInterceptors ?? []),
        ...(this.opts.localInterceptors ?? []),
      ]) {
        try {
          if (interceptor.onFulfilled) {
            processedPayload = await interceptor.onFulfilled(
              processedPayload,
              meta,
            );
          }
        } catch (error) {
          const handled = interceptor.onRejected?.(error);
          const result = handled ? await Promise.resolve(handled) : handled;
          if (result === false) return;
          throw error;
        }
      }

      this.safeOnMessage(processedPayload, meta);
    } catch (error) {
      this.emitStatus("parse-error");
      this.safeOnMessageError(error, rawPayload);
    } finally {
      // 事件级状态重置；retry/id 是连接级，保持记忆
      this.eventData = "";
      this.eventType = "message";
    }
  }

  private parsePayload(rawPayload: string): T {
    if (!rawPayload) return {} as T; // error 事件无 data: 时兜底
    if (this.opts.parse === false) return rawPayload as T;
    return (this.opts.parse ?? JSON.parse)(rawPayload);
  }

  // ─── 安全包装：防止上层回调抛异常中断流 ─────────────────────

  private readonly safeOnMessage = (
    payload: T,
    meta: { event?: string; id?: string; retry?: number },
  ) => {
    try {
      this.callbacks.onMessage?.(payload, meta);
    } catch (error) {
      log.error("onMessage callback error", error);
    }
  };

  private readonly safeOnError = (error: BizApiErrorResponse) => {
    try {
      this.callbacks.onError?.(error);
    } catch (callbackError) {
      log.error("onError callback error", callbackError);
    }
  };

  private readonly safeOnMessageError = (
    error: unknown,
    rawPayload: string,
  ) => {
    try {
      this.callbacks.onMessageError?.(error, rawPayload);
    } catch (callbackError) {
      log.warn("onMessageError callback error", callbackError);
    }
  };

  private readonly safeOnComplete = () => {
    try {
      this.callbacks.onComplete?.();
    } catch (error) {
      log.error("onComplete callback error", error);
    }
  };

  private readonly emitStatus = (status: SseStreamStatus) => {
    try {
      this.callbacks.onStatus?.(status);
    } catch (error) {
      log.warn("onStatus callback error", error);
    }
  };
}
