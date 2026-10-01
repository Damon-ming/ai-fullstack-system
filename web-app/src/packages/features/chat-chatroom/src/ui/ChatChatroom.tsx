import React, { useRef, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { chatMessageHook } from "../hook";

export interface ChatChatroomProps {}
export const ChatChatroom: React.FC<ChatChatroomProps> = () => {
  const { input, setInput, sending, messages, sendStream } = chatMessageHook();
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
      className={`feature-chatroom ${messages.length ? "has-messages" : "is-empty"}`}
    >
      {messages.length > 0 && (
        <section
          ref={messageContainerRef}
          className={`feature-messages flex flex-col gap-8 ${isScrolling ? "is-scrolling" : ""}`}
          onScroll={handleScroll}
          style={{ overflowY: "auto", flex: 1 }}
        >
          {messages.map((message) => {
            return (
              <div
                key={message.id}
                className={`feature-message-row flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
              >
                  <div className={`feature-message-shell ${message.role}`}>
                  <div className={`feature-message-bubble ${message.role}`}>
                    <div
                      className={`feature-message ${message.role}`}
                      style={{
                        maxWidth: message.role === "user" ? "50%" : "100%",
                        wordBreak: "break-word",
                        whiteSpace: "normal",
                      }}
                    >
                      {message.text === "正在思考中..." ? (
                        <span
                          className="feature-thinking"
                          aria-label="正在思考中"
                        >
                          正在思考中
                          <span
                            className="feature-thinking-dots"
                            aria-hidden="true"
                          >
                            <i>.</i>
                            <i>.</i>
                            <i>.</i>
                          </span>
                        </span>
                      ) : message.role === "assistant" ? (
                        <>
                          {message.thinking && (
                            <details className="feature-thinking-content">
                              <summary>思考过程</summary>
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
                      message.text !== "正在思考中..." &&
                      message.msgId && (
                        <div className="feature-message-meta">
                          {message.model && (
                            <span className="feature-meta-item">
                              model: {message.model}
                            </span>
                          )}
                          {message.createdAt && (
                            <span className="feature-meta-item">
                              {new Date(
                                message.createdAt * 1000,
                              ).toLocaleTimeString()}
                            </span>
                          )}
                          {message.traceId && (
                            <span className="feature-meta-item feature-meta-trace"
                                  title={message.traceId}>
                              trace: {message.traceId.slice(0, 8)}…
                            </span>
                          )}
                        </div>
                      )}
                    <button
                      className="feature-copy-button"
                      type="button"
                      aria-label="复制消息"
                      title={copiedMessageId === message.id ? "已复制" : "复制"}
                      onClick={() => void copyMessage(message.text, message.id)}
                    >
                      {copiedMessageId === message.id ? "✓" : "⧉"}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </section>
      )}
      {messages.length > 0 && isUserScrollUp && (
        <button
          className="feature-scroll-bottom"
          type="button"
          aria-label="滚动到底部"
          title="滚动到底部"
          onClick={scrollToBottom}
        >
          ↓
        </button>
      )}
      <style>{thinkingStyles}</style>
      <section className="feature-composer-area">
        {messages.length === 0 && (
          <section className="feature-welcome">
            <div>✦</div>
            <h1>今天想聊点什么？</h1>
            <p>向我提问、写点东西，或上传文件一起分析。</p>
          </section>
        )}
        <footer className="feature-composer">
          <textarea
            ref={composerInputRef}
            className="w-full resize-y overflow-auto whitespace-pre-wrap"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={"输入消息..."}
            disabled={sending}
          />
          <button
            onClick={() => void send()}
            aria-label="发送消息"
            disabled={sending}
          ></button>
        </footer>
      </section>
    </main>
  );
};

const thinkingStyles = `
.feature-thinking-dots{display:inline-flex;min-width:1.2em;text-align:left}
.feature-thinking-dots i{font-style:normal;opacity:0;animation:feature-thinking-dot 1.2s steps(1,end) infinite}
.feature-thinking-dots i:nth-child(2){animation-delay:.4s}
.feature-thinking-dots i:nth-child(3){animation-delay:.8s}
@keyframes feature-thinking-dot{0%,25%{opacity:0}26%,50%{opacity:1}51%,100%{opacity:0}}
.feature-message-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;font-size:11px;color:rgba(120,120,120,.8)}
.feature-meta-item{padding:1px 6px;border-radius:3px;background:rgba(150,150,150,.08)}
.feature-meta-trace{font-family:monospace;cursor:help}
.feature-thinking-content{margin-bottom:8px;padding:6px 10px;border-radius:6px;background:rgba(150,150,150,.06);font-size:13px;color:rgba(120,120,120,.85)}
.feature-thinking-content summary{cursor:pointer;user-select:none}
.feature-thinking-content p{margin:4px 0}
`;
