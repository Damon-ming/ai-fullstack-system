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
  /** 客户端消息 key（React key + 更新定位），与服务端轮次 id 是两个概念 */
  id: string;
  /** 消息正文（用户提问 / 助手回答） */
  content: string;
  role: "user" | "assistant";
  /**
   * 是否仍在等待服务端交付（占位态）。
   * 用显式标记而不是「content === 占位文案」判断：模型真实输出
   * 可能与占位文案相同，字符串比较会误判。
   */
  pending?: boolean;
  /** 推理过程文本（SSE reasoning 事件累加），正文回答在 content */
  reasoning?: string;
  /** 是否正在输出 reasoning */
  isReasoning?: boolean;
  /** reasoning 区域是否折叠 */
  reasoningCollapsed?: boolean;
  /** 本轮异常提示（SSE error / 传输中断 / 落库失败），与正文分离，随历史落库 */
  errorMsg?: string;
  /** 服务端轮次元信息：turnId 与历史记录一致，conversationId 用于后续轮次追加 */
  turnId?: string;
  conversationId?: string;
  /** 提问时刻（Unix 秒），与历史记录 queryAt 同一时刻 */
  queryAt?: number;
}
