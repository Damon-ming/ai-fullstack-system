import { useChatMessageStore } from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";
import { sendChatRoomMessageFn } from "../api";
import type { ChatRoomRequest } from "../api/types";
import { useTranslation } from "@ming/i18n";
import { createLogger } from "@ming/core-log";
import { ErrorCode } from "@ming/biz-common-net-api";
import { resolveChatErrorMessage } from "./useChatSendStreamHook";

const log = createLogger("chat-chatroom/hook/sendNormal");

/** 同步一次性请求（保留备用） */
export function useChatSendNormalHook() {
  const { t } = useTranslation("chat-chatroom");
  const input = useChatMessageStore((s) => s.input);
  const setInput = useChatMessageStore((s) => s.setInput);
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const sending = useChatMessageStore((s) => s.sending);
  const setSending = useChatMessageStore((s) => s.setSending);
  // 当前会话 id：空表示新会话，服务端在响应里下发后回填
  const activeConversationId = useHistoryStore((s) => s.activeConversationId);
  const setActiveConversationId = useHistoryStore(
    (s) => s.setActiveConversationId,
  );
  const markTurnSaved = useHistoryStore((s) => s.markTurnSaved);
  // 是否启用深度推理模式：与流式链路同口径，从全局开关读取
  const reason = useChatMessageStore((s) => s.reason);
  // 取消能力放在全局：切换会话时旧 hook 实例已丢失，只有全局能取消旧流
  const abortNormal = useChatMessageStore((s) => s.abortStream);
  const setAbortController = useChatMessageStore((s) => s.setAbortController);

  const sendNormal = async () => {
    const query = input.trim();
    if (!query || sending) {
      log.debug("sendNormal skipped", { hasQuery: Boolean(query), sending });
      return;
    }
    log.debug("sendNormal started", { queryLength: query.length });

    // 为本次请求创建独立的控制器（先取消上一次，防止并发）
    abortNormal();
    const controller = new AbortController();
    setAbortController(controller);

    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `assistant-${Date.now()}`;
    // 占位文案：服务端尚未交付正文时展示，结束后按实际交付情况清理
    const placeholder = t("reasoning");

    // 预先插入消息，补充role
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

    try {
      const req: ChatRoomRequest = {
        query,
        reason,
        // 已有会话则回传，服务端据此追加；新会话为空，由服务端生成
        conversationId: activeConversationId,
      };
      const res = await sendChatRoomMessageFn(req, controller.signal);
      log.debug("sendNormal succeeded");
      const result = res.data?.data;
      if (result) {
        // 新会话：服务端生成的 conversationId 作为后续轮次的追加目标
        if (!activeConversationId && result.conversationId) {
          setActiveConversationId(result.conversationId);
        }
        setMessages((items) =>
          items.map((msg) =>
            msg.id === assistantMsgId
              ? {
                  ...msg,
                  content: result.content,
                  // 推理文本随正文一并下发；为空则不写，避免空气泡清理误判
                  reasoning: result.reasoning || undefined,
                  pending: false,
                }
              : msg,
          ),
        );
      }
    } catch (e) {
      // 被主动取消时不显示错误
      if (controller.signal.aborted) {
        log.debug("sendNormal aborted by user");
        return;
      }
      const err = e as {
        code?: number;
        data?: { error_msg?: string; conversationId?: string };
      };
      const errMsg = resolveChatErrorMessage(err ?? {}, {
        network: t("error.network"),
        server: t("error.sendFailed"),
      });
      // 拦截轮次：服务端把拦截文案作为正文落库（不是 error_msg），
      // 客户端按正文展示，与流式拦截、历史重载保持同一形态
      const isBlocked =
        err?.code === ErrorCode.CHAT.INPUT_BLOCKED ||
        err?.code === ErrorCode.CHAT.GUARDRAIL_BLOCKED;
      // 失败轮次服务端已落库（finally 兜底）：回填会话 id，后续轮次追加到同一会话
      const conversationId = err?.data?.conversationId;
      if (conversationId && !activeConversationId) {
        setActiveConversationId(conversationId);
      }
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? // 拦截文案有值才按正文展示；为空回退 errorMsg，避免占位消息被清理后丢失这轮
              isBlocked && errMsg
              ? { ...msg, content: errMsg, pending: false }
              : { ...msg, errorMsg: errMsg, pending: false }
            : msg,
        ),
      );
    } finally {
      setAbortController(null);
      setSending(false);
      // 无条件刷新历史列表：落库可能发生在成功 / 失败 / 取消任一路径，
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

  return { sendNormal, abortNormal };
}
