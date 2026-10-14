import { searchItems } from "@ming/feature-search"
import { getHistoryList } from "@ming/feature-history-api"
export const searchHistory = (keyword: string) => searchItems(getHistoryList(), keyword)
