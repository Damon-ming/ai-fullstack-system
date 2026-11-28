import { createAppStore } from "../app-store";

export interface CorpusState {
  open: boolean;
  openCorpus: () => void;
  closeCorpus: () => void;
}

export const useCorpusStore = createAppStore<CorpusState>(
  (set: (partial: Partial<CorpusState>) => void) => ({
    open: false,
    openCorpus: () => set({ open: true }),
    closeCorpus: () => set({ open: false }),
  }),
);
