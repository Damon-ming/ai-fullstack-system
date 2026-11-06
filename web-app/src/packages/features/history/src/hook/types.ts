// history/src/hook/types.ts
/**
 * 模块内部 UI ↔ Hook 通讯类型（非网络请求）。
 */

/** 与 @ming/store 的 ChatMessage 结构兼容（纯类型，避免 feature → store 反向依赖） */
export interface HistoryChatMessage {
  id: string;
  content: string;
  role: "user" | "assistant";
  reasoning?: string;
  errorMsg?: string;
  turnId?: string;
  /** 提问时刻（Unix 秒），与流式 start 事件口径一致，供 UI 渲染时间戳 */
  queryAt?: number;
  /** 历史轮次已结束推理，标题显示「推理过程」 */
  isReasoning?: boolean;
  /** 与流式收尾状态一致：推理区域默认折叠 */
  reasoningCollapsed?: boolean;
}
