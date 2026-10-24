import { createAppStore } from "../app-store";

export interface KnowledgeState {
  open: boolean;
  openKnowledge: () => void;
  closeKnowledge: () => void;
}

export const useKnowledgeStore = createAppStore<KnowledgeState>((set) => ({
  open: false,
  openKnowledge: () => set({ open: true }),
  closeKnowledge: () => set({ open: false }),
}));
