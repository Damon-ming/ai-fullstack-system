import { useSearchStore } from "@ming/store/biz/search-state";

export function useDrawerSearchHook() {
  const openSearch = useSearchStore((s) => s.openSearch);
  return { openSearch };
}
