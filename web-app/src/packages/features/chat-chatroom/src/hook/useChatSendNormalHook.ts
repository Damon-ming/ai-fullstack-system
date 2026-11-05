import { useRef, useCallback } from "react";
import { useChatMessageStore } from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";
import { sendChatRoomMessageFn } from "../api";
import type { ChatRoomRequest } from "../api/types";
import { useTranslation } from "@ming/i18n";
import { createLogger } from "@ming/core-log";

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

  /** 当前进行中的请求控制器，用于主动取消 */
  const abortControllerRef = useRef<AbortController | null>(null);

  /** 取消当前进行中的同步请求 */
  const abortNormal = useCallback(() => {
    if (abortControllerRef.current) {
      log.debug("abortNormal triggered");
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const sendNormal = async () => {
    const query = input.trim();
    if (!query || sending) {
      log.debug("sendNormal skipped", { hasQuery: Boolean(query), sending });
      return;
    }
    log.debug("sendNormal started", { queryLength: query.length });

    // 为本次请求创建独立的控制器（先取消上一次，防止并发）
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `assistant-${Date.now()}`;
    // 占位文案：服务端尚未交付正文时展示，结束后按实际交付情况清理
    const placeholder = t("reasoning");

    // 预先插入消息，补充role
    setMessages((items) => [
      ...items,
      { id: userMsgId, content: query, role: "user" },
      { id: assistantMsgId, content: placeholder, role: "assistant" },
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
                }
              : msg,
          ),
        );
        // 服务端已落库 → 通知历史列表刷新
        markTurnSaved();
      }
    } catch (e) {
      // 被主动取消时不显示错误
      if (controller.signal.aborted) {
        log.debug("sendNormal aborted by user");
        return;
      }
      const errMsg =
        (e instanceof Error
          ? e.message
          : (e as { data?: { error_msg?: string } })?.data?.error_msg) ?? "";
      // 与流式链路保持一致：content 只承载正文，错误单独标记
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId ? { ...msg, errorMsg: errMsg } : msg,
        ),
      );
    } finally {
      abortControllerRef.current = null;
      setSending(false);
      // 空气泡清理：服务端未交付任何内容（无正文 / 推理 / 异常提示）时移除占位消息
      setMessages((prev) =>
        prev.filter((msg) => {
          if (msg.id !== assistantMsgId) return true;
          const hasContent =
            Boolean(msg.content) && msg.content !== placeholder;
          return hasContent || Boolean(msg.reasoning) || Boolean(msg.errorMsg);
        }),
      );
    }
  };

  return { sendNormal, abortNormal };
}
