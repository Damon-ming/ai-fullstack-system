// web-app/src/packages/features/chat-chatroom/src/ui/ChatChatroom.tsx

import React, { useRef, useEffect, useState } from "react";
// SECURITY: react-markdown v9 默认不渲染原始 HTML（<script> 等被转义为纯文本），
// 因此当前配置下反射型 XSS 不成立（P1-12 评估通过）。
// 禁止添加 rehype-raw 插件——它会绕过 HTML 转义，引入 XSS 漏洞。
// 上公网时考虑加 rehype-sanitize 做白名单纵深防御。
import ReactMarkdown from "react-markdown";
import { useChatMessageStateHook } from "../hook/useChatMessageStateHook";
import { useChatSendStreamHook } from "../hook/useChatSendStreamHook";
import { useTranslation } from "@ming/i18n";
import type { ChatMessage } from "@ming/store/biz/chat-state";

/**
 * 单条消息内容渲染 —— 替代原嵌套三元，用早期返回扁平化分支。
 * - 占位消息（"正在思考中..."）：展示脉冲动画
 * - 助手正文：可选 reasoning 面板 + 正文 Markdown
 * - 用户消息：纯文本
 */
function MessageBody({
  message,
  setMessages,
}: Readonly<{
  message: ChatMessage;
  setMessages: (
    updater: ChatMessage[] | ((messages: ChatMessage[]) => ChatMessage[]),
  ) => void;
}>) {
  const { t } = useTranslation("chat-chatroom");

  // 分支 1：流式占位 —— 服务端尚未返回正文
  if (message.text === t("reasoning")) {
    return (
      <span aria-label={t("reasoningAria")}>
        {t("reasoning")}
        <span className="inline-flex min-w-[1.2em] animate-pulse">...</span>
      </span>
    );
  }

  // 分支 2：助手消息 —— 可选 reasoning 折叠面板 + 正文
  if (message.role === "assistant") {
    return (
      <>
        {message.reasoning && (
          <div className="mb-1.5 rounded-lg bg-gray-50 border border-gray-100">
            <button
              type="button"
              onClick={() =>
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === message.id
                      ? { ...m, reasoningCollapsed: !m.reasoningCollapsed }
                      : m,
                  ),
                )
              }
              className="flex w-full items-center gap-1.5 px-3 py-2 text-sm text-gray-500 select-none cursor-pointer"
            >
              <span
                className={`inline-block transition-transform duration-150 text-xs ${
                  message.reasoningCollapsed ? "" : "rotate-90"
                }`}
              >
                ▶
              </span>
              <span className="font-medium">
                {message.isReasoning ? t("reasoning") : t("reasoningProcess")}
              </span>
              {message.isReasoning && (
                <span className="inline-flex min-w-[1.2em] animate-pulse text-gray-400">
                  ...
                </span>
              )}
            </button>
            {!message.reasoningCollapsed && (
              <div className="px-3 pb-2 text-sm text-gray-400 leading-relaxed">
                <ReactMarkdown>{message.reasoning}</ReactMarkdown>
              </div>
            )}
          </div>
        )}
        <div className="text-gray-800">
          <ReactMarkdown>{message.text}</ReactMarkdown>
        </div>
      </>
    );
  }

  // 分支 3：用户消息 —— 纯文本
  return <span className="whitespace-pre-wrap">{message.text}</span>;
}

export const ChatChatroom: React.FC = () => {
  const { t } = useTranslation("chat-chatroom");
  const { input, setInput, sending, messages, setMessages, reason, setReason } =
    useChatMessageStateHook();
  const { sendStream, abortStream } = useChatSendStreamHook();
  const send = sendStream;

  const messageContainerRef = useRef<HTMLDivElement>(null);
  const composerInputRef = useRef<HTMLTextAreaElement>(null);
  const [isUserScrollUp, setIsUserScrollUp] = useState(false);
  const [isScrolling, setIsScrolling] = useState(false);
  const scrollTimerRef = useRef<number | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  const handleScroll = () => {
    const container = messageContainerRef.current;
    if (!container) return;
    setIsScrolling(true);
    if (scrollTimerRef.current !== null)
      window.clearTimeout(scrollTimerRef.current);
    scrollTimerRef.current = window.setTimeout(
      () => setIsScrolling(false),
      700,
    );
    const { scrollTop, scrollHeight, clientHeight } = container;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 10;
    setIsUserScrollUp(!isAtBottom);
  };

  const scrollToBottom = () => {
    const container = messageContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    setIsUserScrollUp(false);
  };

  const copyMessage = async (message: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(message);
    } catch {
      const textArea = document.createElement("textarea");
      textArea.value = message;
      textArea.style.position = "fixed";
      textArea.style.opacity = "0";
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      textArea.remove();
    }
    setCopiedMessageId(messageId);
    window.setTimeout(() => setCopiedMessageId(null), 1200);
  };

  useEffect(() => {
    const container = messageContainerRef.current;
    if (!container || isUserScrollUp) return;
    container.scrollTop = container.scrollHeight;
  }, [messages, isUserScrollUp]);

  useEffect(() => {
    if (!sending) {
      window.requestAnimationFrame(() => composerInputRef.current?.focus());
    }
  }, [sending]);

  useEffect(
    () => () => {
      if (scrollTimerRef.current !== null)
        window.clearTimeout(scrollTimerRef.current);
    },
    [],
  );

  // 页面关闭/刷新前取消进行中的请求，避免服务端继续空跑
  useEffect(() => {
    const handleBeforeUnload = () => {
      abortStream();
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [abortStream]);

  return (
    <main className="flex min-h-0 flex-1 flex-col items-center px-[100px]">
      {/* ===== 消息列表 ===== */}
      {messages.length > 0 && (
        <section
          ref={messageContainerRef}
          onScroll={handleScroll}
          className={`flex w-full min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-4 pb-4 pt-2 ${
            isScrolling ? "scrollbar-visible" : "scrollbar-hidden"
          }`}
          style={{
            scrollbarWidth: "thin",
            scrollbarColor: "transparent transparent",
          }}
        >
          {messages.map((message) => (
            <div
              key={message.id}
              className={`group relative flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div className="relative w-fit max-w-[80%]">
                <div
                  className={`whitespace-normal break-words rounded-2xl px-4 py-3 leading-relaxed ${
                    message.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-800 border border-gray-100 shadow-sm"
                  }`}
                >
                  <MessageBody message={message} setMessages={setMessages} />
                </div>
                {/* 助手消息元信息 */}
                {message.role === "assistant" &&
                  message.text !== t("reasoning") &&
                  message.msgId && (
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-400">
                      {message.createdAt && (
                        <span className="rounded-md bg-gray-50 px-2 py-1">
                          {new Date(
                            message.createdAt * 1000,
                          ).toLocaleTimeString()}
                        </span>
                      )}
                      {message.traceId && (
                        <span
                          className="cursor-help rounded-md bg-gray-50 px-2 py-1 font-mono"
                          title={message.traceId}
                        >
                          trace: {message.traceId.slice(0, 8)}…
                        </span>
                      )}
                    </div>
                  )}
                {/* 复制按钮：AI右下，User左下 */}
                <button
                  type="button"
                  aria-label={t("copy")}
                  title={
                    copiedMessageId === message.id ? t("copied") : t("copy")
                  }
                  onClick={() => void copyMessage(message.text, message.id)}
                  className={`absolute bottom-1 flex h-7 w-7 items-center justify-center rounded-md text-gray-400 opacity-0 transition-all duration-150 hover:bg-gray-100 hover:text-gray-600 group-hover:opacity-100 focus-visible:opacity-100 ${
                    message.role === "user" ? "-left-9" : "-right-9"
                  }`}
                >
                  {copiedMessageId === message.id ? "✓" : "⧉"}
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      {messages.length > 0 && isUserScrollUp && (
        <button
          type="button"
          aria-label={t("scrollToBottomAria")}
          title={t("scrollToBottom")}
          onClick={scrollToBottom}
          className="fixed bottom-28 right-8 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-500 shadow-lg transition-transform hover:-translate-y-0.5 hover:shadow-xl"
        >
          ↓
        </button>
      )}

      {/* ===== 底部输入区域 ===== */}
      <section
        className={`flex w-full flex-col items-center px-4 pb-6 ${
          messages.length === 0 ? "flex-1 justify-center" : "pt-4"
        }`}
      >
        <div className="w-full max-w-[560px]">
          {/* 深度思考开关 */}
          <div className="mb-2 flex justify-center">
            <button
              type="button"
              onClick={() => setReason(!reason)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all ${
                reason
                  ? "bg-purple-100 text-purple-700 ring-1 ring-purple-300"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
              title={t("reasonToggle")}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${reason ? "bg-purple-500" : "bg-gray-400"}`}
              />
              {t("reasonToggle")}
            </button>
          </div>
          <div className="flex items-end gap-2 rounded-2xl border border-gray-200 bg-white px-4 py-3 shadow-lg transition-all focus-within:border-blue-400 focus-within:shadow-xl">
            <textarea
              ref={composerInputRef}
              className="min-h-[24px] max-h-[200px] flex-1 resize-none border-0 bg-transparent text-base leading-6 text-gray-800 outline-0 placeholder:text-gray-400"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={t("input.placeholder")}
              disabled={sending}
              rows={1}
            />
            {sending ? (
              <button
                type="button"
                onClick={() => abortStream()}
                aria-label="取消发送"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-500 text-white transition-all hover:bg-red-600 active:scale-95"
              >
                ✕
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void send()}
                aria-label={t("input.sendAria")}
                disabled={!input.trim()}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white transition-all hover:bg-blue-700 active:scale-95 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
              >
                ↑
              </button>
            )}
          </div>
        </div>
      </section>
    </main>
  );
};
