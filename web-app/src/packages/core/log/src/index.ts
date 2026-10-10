// web-app/src/packages/core/log/src/index.ts
export type LogContext = Record<
  string,
  string | number | boolean | null | undefined
>;

export interface Logger {
  debug(message: string, context?: LogContext): void;
  info(message: string, context?: LogContext): void;
  warn(message: string, context?: LogContext): void;
  error(message: string, error?: unknown, context?: LogContext): void;
}

const format = (namespace: string, message: string, context?: LogContext) => {
  const ts = new Date().toISOString().slice(0, 23); // YYYY-MM-DDTHH:MM:SS.mmm
  const prefix = `[${ts}] [${namespace}]`;
  return context ? [`${prefix} ${message}`, context] : [`${prefix} ${message}`];
};

export function createLogger(namespace: string): Logger {
  return {
    debug: (message, context) =>
      console.debug(...format(namespace, message, context)),
    info: (message, context) =>
      console.info(...format(namespace, message, context)),
    warn: (message, context) =>
      console.warn(...format(namespace, message, context)),
    error: (message, error, context) =>
      console.error(
        ...format(namespace, message, {
          ...context,
          error: error instanceof Error ? error.message : String(error),
        }),
      ),
  };
}

export const logger = createLogger("app");

// ---- 格式化工具 ----
export { formatBody, formatTime } from "./format-utils";
