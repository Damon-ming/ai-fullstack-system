import { useAccountStore } from "@ming/store/biz/account-state";
import { useAccount } from "@ming/feature-account-api";

export function useDrawerAccountHook() {
  const { profile: account } = useAccount();
  const openAccount = useAccountStore((s) => s.openDialog);

  return { account, openAccount };
}
