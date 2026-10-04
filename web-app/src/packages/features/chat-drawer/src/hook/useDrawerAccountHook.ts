import { useAccountStore } from "@ming/store/biz/account-state";

export function useDrawerAccountHook() {
  const account = useAccountStore((s) => s.profile) ?? {
    id: "murphy",
    name: "Murphy",
    avatarText: "M",
  };
  const openAccount = useAccountStore((s) => s.openDialog);

  return { account, openAccount };
}
