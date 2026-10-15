// web-app/src/packages/features/history/src/api/unpack.ts
/**
 * 数据解包工具 —— api 层返回原始 DataApiResponse，
 * hook 层和 historyStore 共享此模块做解包 + 字段映射。
 */

import type { DataApiResponse } from "@ming/data-layer";
import type { HistoryItem, HistoryMessage } from "./types";

/** 解析服务端时间戳（ISO 字符串或 epoch）→ epoch ms。 */
export function parseTimestamp(raw: unknown): number {
  if (!raw) return Date.now();
  const ms = new Date(raw as string).getTime();
  return Number.isNaN(ms) ? Date.now() : ms;
}

/** 解包详情/保存响应 → 原始业务对象 */
export function unpackDetail(res: DataApiResponse<unknown> | undefined): any {
  const d = res?.data as any;
  return d?.conversation ?? d;
}

/** 服务端 list record → 前端 HistoryItem（不含 messages）。 */
export function parseListRecord(item: any): HistoryItem {
  return {
    id: String(item.id),
    title: String(item.title ?? ""),
    meta: String(item.updatedAt || item.updated_at || ""),
    createdAt: parseTimestamp(item.createdAt || item.created_at),
    messages: [],
  };
}

/** 服务端 detail → 前端 HistoryItem（含 messages）。 */
export function parseDetailRecord(detail: any): HistoryItem {
  const messages = parseMessages(detail?.messages);
  return {
    id: String(detail.id),
    title: String(detail.title ?? ""),
    meta: String(detail.updatedAt || detail.updated_at || ""),
    createdAt: parseTimestamp(detail.createdAt || detail.created_at),
    messages,
  };
}

/** 服务端 messages 数组 → 前端 HistoryMessage[]。 */
export function parseMessages(raw: unknown): HistoryMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((m: any) => ({
    id: String(m.id),
    text: String(m.text ?? ""),
    role: m.role === "assistant" ? "assistant" : "user",
  }));
}

/** 解包列表响应 → HistoryItem[] */
export function unpackList(res: DataApiResponse<unknown[]> | undefined): HistoryItem[] {
  const items: any[] = res?.data ?? [];
  return items.map(parseListRecord);
}
