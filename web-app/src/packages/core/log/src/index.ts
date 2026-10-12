// web-app/src/packages/core/log/src/index.ts
export type LogContext = Record<
  string,
  string | number | boolean | null | undefined
>;

export interface Logger {
  debug(message: string, context?: LogContext): void;
  info(message: string, context?: LogContext): void;
  warn(message: string, context?: LogContext): void;

  /**
   * 客户端兜底错误日志 —— 客户端自身捕获并打印。
   * 前缀: CLIENT: [ts] [namespace] [function (file:line)]
   */
  error(message: string, error?: unknown, context?: LogContext): void;

  /**
   * 服务端返回的错误日志 —— 服务端响应中携带的错误信息。
   * 前缀: [ts] [namespace]
   */
  serverError(message: string, error?: unknown, context?: LogContext): void;

  /**
   * 客户端兜底日志 + 抛异常 —— 用于客户端自身 throw 点。
   * 打印 CLIENT: 前缀日志，然后抛出原始 Error。
   */
  throw(error: Error, context?: LogContext): never;

  /**
   * 服务端错误日志 + 抛异常 —— 用于将服务端错误向上层抛出。
   * 打印 前缀日志，然后抛出原始 Error。
   */
  serverThrow(error: Error, context?: LogContext): never;
}

// ---------------------------------------------------------------------------
// 调用位置解析
// ---------------------------------------------------------------------------

interface StackFrame {
  functionName: string;
  file: string;
  line: number;
  column: number;
}

function shortPath(file: string): string {
  const srcIndex = file.lastIndexOf("src/");
  if (srcIndex >= 0) return file.slice(srcIndex);
  const parts = file.split(/[/\\]/);
  return parts.slice(-2).join("/");
}

const STACK_LINE_RE = /at\s+(?:(.+?)\s+\()?(.+?):(\d+):(\d+)\)?\s*$/;

function parseStackFrame(error: Error): StackFrame | null {
  const stack = error.stack;
  if (!stack) return null;

  for (const line of stack.split("\n").slice(1)) {
    if (line.includes("core/log/src")) continue;

    const match = line.match(STACK_LINE_RE);
    if (match) {
      return {
        functionName: match[1] || "<anonymous>",
        file: match[2],
        line: parseInt(match[3], 10),
        column: parseInt(match[4], 10),
      };
    }
  }
  return null;
}

function callerLocation(): string {
  const frame = parseStackFrame(new Error());
  if (!frame) return "";
  return `${frame.functionName} (${shortPath(frame.file)}:${frame.line})`;
}

// ---------------------------------------------------------------------------
// 格式化
// ---------------------------------------------------------------------------

function format(
  namespace: string,
  message: string,
  context?: LogContext,
): unknown[] {
  const ts = new Date().toISOString().slice(0, 23);
  const location = ` [${callerLocation()}]`;
  const line = `[${ts}] [${namespace}]${location} ${message}`;
  return context ? [line, context] : [line];
}

function formatClientError(
  namespace: string,
  message: string,
  error: Error,
  context?: LogContext,
): unknown[] {
  const ts = new Date().toISOString().slice(0, 23);
  const frame = parseStackFrame(error);
  const location = frame
    ? `${frame.functionName} (${shortPath(frame.file)}:${frame.line})`
    : "<unknown location>";

  const output: unknown[] = [
    `CLIENT: [${ts}] [${namespace}] [${location}] ${message}: ${error.message}`,
  ];
  if (error.stack) output.push(`\n${error.stack}`);
  return output;
}

function errorDetail(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "object" && error !== null) {
    try {
      return JSON.stringify(error);
    } catch {
      return String(error);
    }
  }
  return String(error ?? "");
}

function formatServerError(
  namespace: string,
  message: string,
  error: unknown,
  context?: LogContext,
): unknown[] {
  const ts = new Date().toISOString().slice(0, 23);
  const output: unknown[] = [
    `[${ts}] [${namespace}] ${message}: ${errorDetail(error)}`,
  ];
  if (error instanceof Error && error.stack) {
    output.push(`\n${error.stack}`);
  }
  return output;
}

// ---------------------------------------------------------------------------
// Logger 工厂
// ---------------------------------------------------------------------------

export function createLogger(namespace: string): Logger {
  return {
    debug: (message, context) =>
      console.debug(...format(namespace, message, context)),
    info: (message, context) =>
      console.info(...format(namespace, message, context)),
    warn: (message, context) =>
      console.warn(...format(namespace, message, context)),
    error: (message, error, context) => {
      if (error instanceof Error) {
        console.error(...formatClientError(namespace, message, error, context));
      } else {
        console.error(
          ...format(namespace, message, {
            ...context,
            error: String(error ?? ""),
          }),
        );
      }
    },
    serverError: (message, error, context) => {
      console.error(...formatServerError(namespace, message, error, context));
    },
    throw: (error, context) => {
      console.error(
        ...formatClientError(namespace, "Client exception", error, context),
      );
      throw error;
    },
    serverThrow: (error, context) => {
      console.error(
        ...formatServerError(
          namespace,
          "Server error propagated",
          error,
          context,
        ),
      );
      throw error;
    },
  };
}

export const logger = createLogger("app");

// ---- 格式化工具 ----
export { formatBody, formatTime } from "./format-utils";
