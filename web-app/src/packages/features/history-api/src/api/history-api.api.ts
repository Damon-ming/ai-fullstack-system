import { historyActions } from "@ming/feature-history"
import type { HistoryMessage } from "@ming/feature-history"
export { useHistory } from "@ming/feature-history"

export const getHistoryList = () => historyActions.list()
export const addHistory = (title: string) => historyActions.add(title)
export const removeHistory = (id: string) => historyActions.remove(id)
export const getHistoryMessages = (id: string) => historyActions.messages(id)
export const saveHistoryMessages = (title: string, messages: HistoryMessage[]) => historyActions.saveMessages(title, messages)
