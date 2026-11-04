/** 一轮问答（四个时间点，时长由展示方派生） */
export interface HistoryTurn {
  turnId: string;
  query: string;
  reasoning: string;
  content: string;
  /** 本轮异常提示（用户可见文案，成功时为空） */
  errorMsg: string;
  queryAt: string;
  firstTokenAt: string;
  reasoningDoneAt: string;
  answeredAt: string;
}

export interface HistoryItem {
  /** 会话唯一标识 */
  conversationId: string;
  title: string;
  /** 创建时间 ISO8601 */
  createdAt: string;
  /** 更新时间 ISO8601（列表按此倒序分组） */
  updatedAt: string;
  turns?: HistoryTurn[];
}
