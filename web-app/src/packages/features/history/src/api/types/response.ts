/** 一轮问答（四个时间点，时长由展示方派生） */
export interface HistoryTurn {
  turnId: string;
  query: string;
  reasoning: string;
  content: string;
  queryAt: string;
  firstTokenAt: string;
  reasoningDoneAt: string;
  answeredAt: string;
}

export interface HistoryItem {
  id: string;
  title: string;
  meta: string;
  createdAt: number;
  turns?: HistoryTurn[];
}
