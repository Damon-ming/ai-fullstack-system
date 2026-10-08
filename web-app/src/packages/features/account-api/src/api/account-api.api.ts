import {
  useAccount,
  accountActions,
  getDeviceToken,
  initDeviceToken,
} from "@ming/features-account"

export { useAccount } from "@ming/features-account"
export type { AccountProfile } from "@ming/features-account"

export const getCurrentAccount = () => accountActions.current()
export const updateAccount = (name: string) => accountActions.update(name)
export const getDeviceToken = () => getDeviceToken()
export const initDeviceToken = () => initDeviceToken()
