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
    <main
      className={`flex min-h-0 flex-1 flex-col items-center px-7 py-8 ${
        messages.length === 0 ? "justify-center" : ""
      }`}
    >
      {messages.length > 0 && (
        <section
          ref={messageContainerRef}
          onScroll={handleScroll}
          className={`flex w-full min-h-0 flex-1 flex-col gap-8 overflow-y-auto py-2 ${
            isScrolling ? "is-scrolling" : ""
          }`}
          style={{
            scrollbarWidth: "thin",
            scrollbarColor: "transparent transparent",
          }}
        >
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`group relative flex w-full items-end ${message.role === "user" ? "justify-end pr-11" : "pr-2.5"}`}
              >
                <div
                  className={`relative w-fit ${message.role === "user" ? "max-w-[50%]" : "max-w-full"}`}
                >
                  <div
                    className={`whitespace-normal break-words rounded-2xl px-4 py-3 leading-relaxed ${
                      message.role === "user"
                        ? "rounded-br-sm bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-500/20"
                        : "rounded-bl-sm border border-slate-200 bg-white/80 text-slate-700 shadow-sm"
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
                          <details className="mb-1.5 rounded-md bg-gray-500/5 px-2.5 py-1.5 text-sm text-gray-500/85">
                            <summary className="cursor-pointer select-none">
                              {t("thinkingProcess")}
                            </summary>
                            <ReactMarkdown>{message.thinking}</ReactMarkdown>
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
                  {/* 助手消息元信息 —— 由 SSE start 事件携带 */}
                  {message.role === "assistant" &&
                    message.text !== t("thinking") &&
                    message.msgId && (
                      <div className="mt-1.5 flex flex-wrap gap-2 text-xs text-gray-500/70">
                        {message.model && (
                          <span className="rounded bg-gray-500/5 px-1.5 py-0.5">
                            model: {message.model}
                          </span>
                        )}
                        {message.createdAt && (
                          <span className="rounded bg-gray-500/5 px-1.5 py-0.5">
                            {new Date(
                              message.createdAt * 1000,
                            ).toLocaleTimeString()}
                          </span>
                        )}
                        {message.traceId && (
                          <span
                            className="cursor-help rounded bg-gray-500/5 px-1.5 py-0.5 font-mono"
                            title={message.traceId}
                          >
                            trace: {message.traceId.slice(0, 8)}…
                          </span>
                        )}
                      </div>
                    )}
                  <button
                    type="button"
                    aria-label={t("copy")}
                    title={
                      copiedMessageId === message.id ? t("copied") : t("copy")
                    }
                    onClick={() => void copyMessage(message.text, message.id)}
                    className="absolute -right-9 bottom-2.5 h-[27px] w-[27px] rounded-lg border border-slate-200 bg-white/95 text-sm text-indigo-500 opacity-0 transition-all duration-150 hover:bg-indigo-50 group-hover:opacity-100 focus-visible:opacity-100"
                    style={{ transform: "translateY(4px)" }}
                  >
                    {copiedMessageId === message.id ? "✓" : "⧉"}
                  </button>
                </div>
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
          className="absolute bottom-[90px] right-[18px] z-10 flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white/96 text-lg text-indigo-500 shadow-lg transition-transform hover:-translate-y-0.5"
        >
          ↓
        </button>
      )}

      <section className="flex w-full max-w-[900px] flex-col">
        {messages.length === 0 && (
          <section className="m-auto text-center">
            <div className="mx-auto flex h-[66px] w-[66px] items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-[32px] text-white shadow-lg shadow-indigo-500/25">
              ✦
            </div>
            <h1 className="mt-5 text-[31px] font-semibold tracking-tight text-slate-800">
              {t("welcome.title")}
            </h1>
            <p className="mt-2 text-sm text-slate-400">
              {t("welcome.subtitle")}
            </p>
          </section>
        )}
        <footer className="flex items-end gap-2.5 rounded-2xl border border-slate-200 bg-white/92 px-3.5 py-3 shadow-xl transition-all focus-within:-translate-y-0.5 focus-within:border-indigo-300 focus-within:shadow-lg">
          <textarea
            ref={composerInputRef}
            className="min-h-[36px] max-h-[140px] flex-1 resize-none border-0 bg-transparent leading-6 text-slate-700 outline-0 placeholder:text-slate-400"
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
          />
          <button
            type="button"
            onClick={() => void send()}
            aria-label={t("input.sendAria")}
            disabled={sending}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-lg text-white shadow-lg shadow-indigo-500/20 transition-all hover:-translate-y-0.5 hover:brightness-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
          >
            ↑
          </button>
        </footer>
      </section>
    </main>
  );
};
