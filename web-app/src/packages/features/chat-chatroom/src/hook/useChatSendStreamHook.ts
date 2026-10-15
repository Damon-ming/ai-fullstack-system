import { useRef, useCallback } from "react";
import { useChatMessageStore } from "@ming/store/biz/chat-state";
import { streamChatRoomMessage } from "../api";
import type { ChatRoomRequest, ChatStartData } from "../api/types";
import { useTranslation } from "@ming/i18n";
import { createLogger } from "@ming/core-log";

const log = createLogger("chat-chatroom/hook/sendStream");

/** SSE 流式请求（默认使用） */
export function useChatSendStreamHook() {
  const { t } = useTranslation("chat-chatroom");
  const input = useChatMessageStore((s) => s.input);
  const setInput = useChatMessageStore((s) => s.setInput);
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const sending = useChatMessageStore((s) => s.sending);
  const setSending = useChatMessageStore((s) => s.setSending);
  const reason = useChatMessageStore((s) => s.reason);
  const setReason = useChatMessageStore((s) => s.setReason);

  /** 当前进行中的 SSE 请求控制器，用于主动取消 */
  const abortControllerRef = useRef<AbortController | null>(null);

  /** 取消当前进行中的 SSE 请求 */
  const abortStream = useCallback(() => {
    if (abortControllerRef.current) {
      log.debug("abortStream triggered");
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const sendStream = async () => {
    const query = input.trim();
    if (!query || sending) {
      log.debug("sendStream skipped", { hasQuery: Boolean(query), sending });
      return;
    }
    log.debug("sendStream started", { queryLength: query.length });
    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `assistant-${Date.now()}`;

    setMessages((items) => [
      ...items,
      { id: userMsgId, text: query, role: "user" },
      { id: assistantMsgId, text: t("reasoning"), role: "assistant" },
    ]);
    setInput("");
    setSending(true);

    // 为本次请求创建独立的控制器（先取消上一次，防止并发）
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    let firstChunk = true;
    let streamFinished = false;

    try {
      const req: ChatRoomRequest = { query, reason };

      await streamChatRoomMessage(req, {
        // meta.event 来自 SSE 协议 event: 字段，payload 是解析后的 data JSON
        onMessage: (payload, meta) => {
          const eventType = meta?.event;
          log.debug("sendStream received event", { event: eventType });

          if (eventType === "start") {
            // 记录本次会话的元信息，挂到 assistant 消息上供 UI 展示
            const startData = payload.data as ChatStartData;
            log.debug("sendStream start metadata", {
              msgId: startData.msgId,
              model: startData.model,
            });
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId
                  ? {
                      ...msg,
                      msgId: startData.msgId,
                      conversationId: startData.conversationId,
                      model: startData.model,
                      createdAt: startData.createdAt,
                      traceId: startData.traceId,
                    }
                  : msg,
              ),
            );
          } else if (eventType === "reasoning") {
            // 推理过程分片 —— 累加到 reasoning 字段，不干扰正文
            const data = payload.data as { content: string };
            const reasoning = data.content || "";
            if (reasoning) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? {
                        ...msg,
                        reasoning: (msg.reasoning ?? "") + reasoning,
                        isReasoning: true,
                      }
                    : msg,
                ),
              );
            }
          } else if (eventType === "delta") {
            const data = payload.data as { content: string };
            const delta = data.content || "";
            // 首包为空时不翻转 firstChunk，保留"正在思考中..."占位，避免闪烁
            if (firstChunk) {
              if (delta) {
                firstChunk = false;
                // 正文开始输出 → 自动折叠 reasoning 区域
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, text: delta, isReasoning: false, reasoningCollapsed: true }
                      : msg,
                  ),
                );
              }
              return;
            }
            if (delta) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, text: msg.text + delta }
                    : msg,
                ),
              );
            }
          } else if (eventType === "done") {
            streamFinished = true;
          } else if (eventType === "error") {
            streamFinished = true;
            const errData = payload.data as { error_msg: string };
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId
                  ? { ...msg, text: `请求异常：${errData.error_msg}` }
                  : msg,
              ),
            );
          }
        },
        onError: (error) => {
          streamFinished = true;
          const message =
            error.data?.error_msg || t("error.streamFailed");
          log.error("sendStream response failed", error);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId ? { ...msg, text: message } : msg,
            ),
          );
        },
      }, { signal: controller.signal });
    } catch (e) {
      // 被主动取消时不显示错误
      if (controller.signal.aborted) {
        log.debug("sendStream aborted by user");
        return;
      }
      log.error("sendStream failed", e);
      const errMsg = e instanceof Error ? e.message : t("error.sendFailed");
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId ? { ...msg, text: errMsg } : msg,
        ),
      );
    } finally {
      abortControllerRef.current = null;
      log.debug("sendStream finished", { streamFinished });
      // 无论正常完成、服务端 error 还是网络异常，都释放输入框和发送按钮状态。
      setSending(false);
    }
  };

  return { sendStream, abortStream, reason, setReason };
}
