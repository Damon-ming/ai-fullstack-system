import { createAppStore } from "../app-store";

export interface AccountState {
  dialogOpen: boolean;
  draftName: string;
  openDialog: (name: string) => void;
  closeDialog: () => void;
  setDraftName: (name: string) => void;
}

export const useAccountStore = createAppStore<AccountState>((set) => ({
  dialogOpen: false,
  draftName: "",
  openDialog: (draftName) => set({ dialogOpen: true, draftName }),
  closeDialog: () => set({ dialogOpen: false }),
  setDraftName: (draftName) => set({ draftName }),
}));
