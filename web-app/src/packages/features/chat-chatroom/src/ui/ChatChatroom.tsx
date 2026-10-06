// web-app/src/packages/features/chat-chatroom/src/ui/ChatChatroom.tsx

import React, { useRef, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useChatMessageStateHook } from "../hook/useChatMessageStateHook";
import { useChatSendStreamHook } from "../hook/useChatSendStreamHook";
import { useTranslation } from "@ming/i18n";

export const ChatChatroom: React.FC = () => {
  const { t } = useTranslation("chat-chatroom");
  const { input, setInput, sending, messages } = useChatMessageStateHook();
  const { sendStream } = useChatSendStreamHook();
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
                  {message.text === t("thinking") ? (
                    <span aria-label={t("thinkingAria")}>
                      {t("thinking")}
                      <span className="inline-flex min-w-[1.2em] animate-pulse">
                        ...
                      </span>
                    </span>
                  ) : message.role === "assistant" ? (
                    <>
                      {message.thinking && (
                        <details className="mb-1.5 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-500 border border-gray-100">
                          <summary className="cursor-pointer select-none font-medium">
                            {t("thinkingProcess")}
                          </summary>
                          <div className="mt-2">
                            <ReactMarkdown>{message.thinking}</ReactMarkdown>
                          </div>
                        </details>
                      )}
                      <ReactMarkdown>{message.text}</ReactMarkdown>
                    </>
                  ) : (
                    <span className="whitespace-pre-wrap">
                      {message.text}
                    </span>
                  )}
                </div>
                {/* 助手消息元信息 */}
                {message.role === "assistant" &&
                  message.text !== t("thinking") &&
                  message.msgId && (
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-400">
                      {message.model && (
                        <span className="rounded-md bg-gray-50 px-2 py-1">
                          model: {message.model}
                          <span className="sr-only">model: {message.model}</span>
                        </span>
                      )}
                      {message.createdAt && (
                        <span className="rounded-md bg-gray-50 px-2 py-1">
                          {new Date(message.createdAt * 1000).toLocaleTimeString()}
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
                  title={copiedMessageId === message.id ? t("copied") : t("copy")}
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
            <button
              type="button"
              onClick={() => void send()}
              aria-label={t("input.sendAria")}
              disabled={sending || !input.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white transition-all hover:bg-blue-700 active:scale-95 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
            >
              {sending ? "◌" : "↑"}
            </button>
          </div>
        </div>
      </section>
    </main>
  );
};
