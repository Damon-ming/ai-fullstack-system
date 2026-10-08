// web-app/src/packages/features/account/src/hook/AccountHook.ts
import { useState } from "react";
import { accountStore, getDeviceToken } from "../api";

export function useAccount() {
  const [profile, setProfile] = useState(() => accountStore.current());
  const update = (name: string) => {
    const next = accountStore.update(name);
    setProfile(next);
    return next;
  };
  return { profile, update };
}

export const accountActions = {
  current: () => accountStore.current(),
  update: (name: string) => accountStore.update(name),
  getToken: () => getDeviceToken(),
};
