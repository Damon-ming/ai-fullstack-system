import { useChatMessageStore } from "@ming/store/biz/chat-state";
import { ChatRoomRequest } from "../api/types";
import { sendChatRoomMessage, streamChatRoomMessage } from "../api";
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
        const res = await sendChatRoomMessage(req);
        log.debug("sendNormal succeeded");
        const result = res.data?.result;
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
        onMessage: (payload) => {
        log.debug("sendStream received event", { event: payload.event });
        if (payload.event === "delta") {
          const data = payload.data as { answer_content: string };
          const delta = data.answer_content || "";
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
        } else if (payload.event === "done") {
          streamFinished = true;
        } else if (payload.event === "error") {
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
          const httpCode = error.clientErrData?.httpCode;
          const message = error.clientErrData?.message || "流式请求失败";
          const errorText = httpCode
            ? `请求失败（HTTP ${httpCode}）：${message}`
            : message;
          log.error("sendStream response failed", error, { httpCode });
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
