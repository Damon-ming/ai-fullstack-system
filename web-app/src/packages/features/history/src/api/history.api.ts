import { getJson, setJson } from "@ming/core-storage";
import type { HistoryItem, HistoryMessage } from "./types/response";

const key = "ming-ai-history";

const read = (): HistoryItem[] => {
  try {
    const value = getJson<unknown>(key);
    if (!Array.isArray(value)) return [];
    return value.filter((item) => !["welcome", "design", "plan"].includes(item.id)).map((item) => {
      const legacyTimestamp = typeof item.id === "string" && item.id.startsWith("local-") ? Number(item.id.slice(6)) : 0;
      return { ...item, createdAt: typeof item.createdAt === "number" ? item.createdAt : legacyTimestamp || Date.now() };
    });
  } catch {
    return [];
  }
};

const write = (items: HistoryItem[]) => {
  setJson(key, items);
};

export const historyStore = {
  list(): HistoryItem[] {
    return read();
  },
  add(title: string) {
    const items = read().filter((item) => item.title !== title);
    const next = [{ id: `local-${Date.now()}`, title, meta: "刚刚", createdAt: Date.now() }, ...items];
    write(next);
    return next[0];
  },
  saveMessages(title: string, messages: HistoryMessage[]) {
    const items = read();
    const existing = items.find((item) => item.title === title);
    if (existing) {
      existing.messages = messages;
    } else {
      items.unshift({ id: `local-${Date.now()}`, title, meta: "刚刚", createdAt: Date.now(), messages });
    }
    write(items);
    return items.find((item) => item.title === title);
  },
  messages(id: string): HistoryMessage[] {
    return read().find((item) => item.id === id)?.messages || [];
  },
  remove(id: string) {
    write(read().filter((item) => item.id !== id));
  },
};
