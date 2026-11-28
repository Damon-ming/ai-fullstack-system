import { createAppStore } from "../app-store";

export interface AccountProfileState {
  userId: number | null;
  name: string;
  nickname: string;
  avatarText: string;
}

export interface AccountState {
  profile: AccountProfileState;
  setProfile: (profile: AccountProfileState) => void;
  dialogOpen: boolean;
  draftNickname: string;
  openDialog: (nickname: string) => void;
  closeDialog: () => void;
  setDraftNickname: (nickname: string) => void;
}

export const useAccountStore = createAppStore<AccountState>((set) => ({
  profile: { userId: null, name: "", nickname: "", avatarText: "" },
  setProfile: (profile) => set({ profile }),
  dialogOpen: false,
  draftNickname: "",
  openDialog: (draftNickname) => set({ dialogOpen: true, draftNickname }),
  closeDialog: () => set({ dialogOpen: false }),
  setDraftNickname: (draftNickname) => set({ draftNickname }),
}));
