import { createAppStore } from "../app-store";
import type { AccountProfile } from "@ming/feature-account-api";

export interface AccountState {
  dialogOpen: boolean;
  draftName: string;
  profile: AccountProfile | null;
  openDialog: (name: string) => void;
  closeDialog: () => void;
  setDraftName: (name: string) => void;
  setProfile: (profile: AccountProfile) => void;
}

export const useAccountStore = createAppStore<AccountState>((set) => ({
  dialogOpen: false,
  draftName: "",
  profile: null,
  openDialog: (draftName) => set({ dialogOpen: true, draftName }),
  closeDialog: () => set({ dialogOpen: false }),
  setDraftName: (draftName) => set({ draftName }),
  setProfile: (profile) => set({ profile }),
}));
