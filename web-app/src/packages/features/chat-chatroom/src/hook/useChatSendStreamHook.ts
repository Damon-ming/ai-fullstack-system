import { useChatMessageStore } from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";
import { streamChatRoomMessage } from "../api";
import type { ChatRoomRequest, ChatStartData } from "../api/types";
import { useTranslation } from "@ming/i18n";
import { createLogger } from "@ming/core-log";
import { ClientErrorCode } from "@ming/biz-common-net-api";

const log = createLogger("chat-chatroom/hook/sendStream");

/** 格式化消息时间戳（unix秒 → 本地时间字符串）供 UI 直接渲染 */
export function formatMessageTime(unixSeconds: number | undefined): string {
  return unixSeconds ? new Date(unixSeconds * 1000).toLocaleTimeString() : "";
}

/**
 * 解析用户可见的错误文案。
 * - 客户端侧错误（网络异常等）：服务端没有对应记录，用本地化文案，
 *   避免把内部 CLIENT: 标记展示给用户
 * - 服务端错误：优先用服务端脱敏文案，缺失时才用本地化兜底
 */
export function resolveChatErrorMessage(
  error: { code?: number; data?: { error_msg?: string } },
  fallbacks: { network: string; server: string },
): string {
  if (
    error.code === ClientErrorCode.NET_TIMEOUT ||
    error.code === ClientErrorCode.NET_UNREACHABLE ||
    error.code === ClientErrorCode.CONFIG_ERR
  ) {
    return fallbacks.network;
  }
  return error.data?.error_msg || fallbacks.server;
}

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
  // 当前会话 id：空表示新会话，服务端在 start 事件下发后回填
  const activeConversationId = useHistoryStore((s) => s.activeConversationId);
  const setActiveConversationId = useHistoryStore(
    (s) => s.setActiveConversationId,
  );
  const markTurnSaved = useHistoryStore((s) => s.markTurnSaved);
  // 取消能力放在全局：切换会话时旧 hook 实例已丢失，只有全局能取消旧流
  const abortStream = useChatMessageStore((s) => s.abortStream);
  const setAbortController = useChatMessageStore((s) => s.setAbortController);

  const sendStream = async () => {
    const query = input.trim();
    if (!query || sending) {
      log.debug("sendStream skipped", { hasQuery: Boolean(query), sending });
      return;
    }
    log.debug("sendStream started", { queryLength: query.length });
    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `assistant-${Date.now()}`;
    // 占位文案：服务端尚未交付正文时展示，流结束后按实际交付情况清理
    const placeholder = t("reasoning");

    setMessages((items) => [
      ...items,
      { id: userMsgId, content: query, role: "user" },
      // pending 标记占位态，避免依赖「content === 占位文案」的字符串比较
      {
        id: assistantMsgId,
        content: placeholder,
        role: "assistant",
        pending: true,
      },
    ]);
    setInput("");
    setSending(true);

    // 为本次请求创建独立的控制器（先取消上一次，防止并发）
    abortStream();
    const controller = new AbortController();
    setAbortController(controller);

    let firstChunk = true;
    let streamFinished = false;

    try {
      const req: ChatRoomRequest = {
        query,
        reason,
        // 已有会话则回传，服务端据此追加；新会话为空，由服务端生成
        conversationId: activeConversationId,
      };

      await streamChatRoomMessage(
        req,
        {
          // meta.event 来自 SSE 协议 event: 字段，payload 是解析后的 data JSON
          onMessage: (payload, meta) => {
            const eventType = meta?.event;
            log.debug("sendStream received event", { event: eventType });

            if (eventType === "start") {
              // 记录本次轮次元信息，挂到 assistant 消息上供 UI 展示
              const startData = payload.data as ChatStartData;
              log.debug("sendStream start metadata", {
                turnId: startData.turnId,
              });
              // 新会话：服务端生成的 conversationId 作为后续轮次的追加目标
              if (!activeConversationId && startData.conversationId) {
                setActiveConversationId(startData.conversationId);
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? {
                        ...msg,
                        turnId: startData.turnId,
                        conversationId: startData.conversationId,
                        queryAt: startData.queryAt,
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
                          pending: false,
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
                        ? {
                            ...msg,
                            content: delta,
                            isReasoning: false,
                            reasoningCollapsed: true,
                            pending: false,
                          }
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
                      ? { ...msg, content: msg.content + delta }
                      : msg,
                  ),
                );
              }
            } else if (eventType === "done") {
              streamFinished = true;
            }
            // 注：SSE error 事件由解析层路由到 onError，不会进入 onMessage
          },
          onError: (error) => {
            streamFinished = true;
            // 主动取消：不展示客户端文案（服务端已交付内容仍会落库）
            if (controller.signal.aborted) {
              log.debug("sendStream aborted by user");
              return;
            }
            const message = resolveChatErrorMessage(error, {
              network: t("error.network"),
              server: t("error.streamFailed"),
            });
            log.error("sendStream response failed", error);
            // 只标记错误，不覆盖 content —— 已流式显示的内容要原样保留，
            // 让「用户看到的」等于服务端实际交付的内容
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId
                  ? { ...msg, errorMsg: message, pending: false }
                  : msg,
              ),
            );
          },
        },
        { signal: controller.signal },
      );
    } catch (e) {
      // streamChatRoomMessage 内部已吞掉异常（返回 SseFinalState），
      // 这里是兜底：真抛出来时同样只标记错误，保留已显示内容
      log.error("sendStream failed", e);
      if (controller.signal.aborted) {
        log.debug("sendStream aborted by user");
      } else {
        const errMsg =
          e instanceof Error
            ? e.message
            : resolveChatErrorMessage(
                e as { code: number; data?: { error_msg?: string } },
                { network: t("error.network"), server: t("error.sendFailed") },
              );
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, errorMsg: errMsg, pending: false }
              : msg,
          ),
        );
      }
    } finally {
      setAbortController(null);
      log.debug("sendStream finished", { streamFinished });
      // 无论正常完成、服务端 error 还是网络异常，都释放输入框和发送按钮状态。
      setSending(false);
      // 无条件刷新历史列表：落库可能发生在 done 之前（done 丢失时），
      // 只有向服务端对齐才能保证抽屉内容与 DB 一致
      markTurnSaved();
      // 空气泡清理：与 DB 落库口径一致（content || reasoning || error_msg），
      // 未交付任何内容时移除占位消息；pending 标记代替占位文案字符串比较
      setMessages((prev) =>
        prev.filter((msg) => {
          if (msg.id !== assistantMsgId) return true;
          return (
            !msg.pending || Boolean(msg.reasoning) || Boolean(msg.errorMsg)
          );
        }),
      );
    }
  };

  return { sendStream, abortStream, reason, setReason };
}
