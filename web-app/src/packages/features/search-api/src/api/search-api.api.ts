import { searchItems } from "@ming/feature-search"
import type { HistoryItem } from "@ming/feature-history-api"

/**
 * 对话历史搜索 —— 对已加载的 history 列表做本地过滤。
 * 消费方通过 useHistory().list 拿到缓存列表后传入。
 */
export const searchHistory = (items: HistoryItem[], keyword: string) =>
  searchItems(items, keyword)
