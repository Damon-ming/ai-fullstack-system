// web-app/src/packages/features/chat-chatroom/src/hook/types.ts
/**
 * 模块内部 UI ↔ Hook 通讯类型。
 *
 * 定义 chat-chatroom 模块的消息类型，避免 UI 层直连 @ming/store 内部类型。
 * store 的 chat-state.ts 实现此接口，但 feature 模块通过本类型引用，
 * 不直接 import store 类型定义。
 */

/** 单条聊天消息（feature 层视图模型，独立于 store 实现） */
export interface ChatMessage {
  id: string;
  text: string;
  role: "user" | "assistant";
  /** 推理过程文本（SSE reasoning 事件累加），正文回答在 text */
  reasoning?: string;
  /** 是否正在输出 reasoning */
  isReasoning?: boolean;
  /** reasoning 区域是否折叠 */
  reasoningCollapsed?: boolean;
  /** SSE start 事件携带的元信息 */
  msgId?: string;
  conversationId?: string;
  model?: string;
  createdAt?: number;
  traceId?: string;
}
