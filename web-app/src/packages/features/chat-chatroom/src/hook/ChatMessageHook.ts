import { useChatMessageStore } from "@ming/store/biz/chat-state";
import { ChatStartData, ChatRoomRequest } from "../api/types";
import { sendChatRoomMessageFn, streamChatRoomMessage } from "../api";
import { createLogger } from "@ming/core-log";

const log = createLogger("chat-chatroom/hook");

export function chatMessageHook() {
  const { input, setInput, messages, setMessages, sending, setSending } =
    useChatMessageStore();

  // 同步一次性请求（保留备用）
  const sendNormal = async () => {
    const query = input.trim();
    if (!query || sending) {
      log.debug("sendNormal skipped", { hasQuery: Boolean(query), sending });
      return;
    }
    log.debug("sendNormal started", { queryLength: query.length });

    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `assistant-${Date.now()}`;

    // 预先插入消息，补充role
    setMessages((items) => [
      ...items,
      { id: userMsgId, text: query, role: "user" },
      { id: assistantMsgId, text: "正在思考中...", role: "assistant" },
    ]);
    setInput("");
    setSending(true);

    try {
      const req: ChatRoomRequest = {
        query,
        think: false,
      };
      const res = await sendChatRoomMessageFn(req);
      log.debug("sendNormal succeeded");
      const result = res.data?.data;
      if (result) {
        setMessages((items) =>
          items.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, text: result.answer_content }
              : msg,
          ),
        );
      }
    } catch (e) {
      log.error("sendNormal failed", e);
      const errMsg =
        e instanceof Error ? e.message : "消息发送失败，请稍后重试";
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId ? { ...msg, text: `${errMsg}` } : msg,
        ),
      );
    } finally {
      setSending(false);
    }
  };

  // SSE流式（默认使用）
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
      { id: assistantMsgId, text: "正在思考中...", role: "assistant" },
    ]);
    setInput("");
    setSending(true);

    let firstChunk = true;
    let streamFinished = false;

    try {
      const req: ChatRoomRequest = {
        query,
        think: false,
      };

      await streamChatRoomMessage(req, {
        // meta.event 来自 SSE 协议 event: 字段，payload 是解析后的 data JSON
        onMessage: (payload, meta) => {
          const eventType = meta?.event;
          log.debug("sendStream received event", { event: eventType });

          if (eventType === "start") {
            // 记录本次会话的元信息，挂到 assistant 消息上供 UI 展示
            const startData = payload.data as ChatStartData;
            log.debug("sendStream start metadata", { startData });
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
          } else if (eventType === "thinking") {
            // 思考过程分片 —— 累加到 thinking 字段，不干扰正文
            const data = payload.data as { content: string };
            const thinking = data.content || "";
            if (thinking) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMsgId
                    ? { ...msg, thinking: (msg.thinking ?? "") + thinking }
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
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId ? { ...msg, text: delta } : msg,
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
          const message = error.clientData?.message || "流式请求失败";
          const errorText = message;
          log.error("sendStream response failed", error);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId ? { ...msg, text: errorText } : msg,
            ),
          );
        },
      });
    } catch (e) {
      log.error("sendStream failed", e);
      const errMsg =
        e instanceof Error ? e.message : "消息发送失败，请稍后重试";
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId ? { ...msg, text: `${errMsg}` } : msg,
        ),
      );
    } finally {
      log.debug("sendStream finished", { streamFinished });
      // 无论正常完成、服务端 error 还是网络异常，都释放输入框和发送按钮状态。
      setSending(false);
    }
  };

  return {
    input,
    setInput,
    messages,
    sending,
    sendNormal,
    sendStream,
  };
}
