import { useChatUiStore } from "@ming/store/biz/chat-state";

export function useDrawerHeaderHook() {
  const open = useChatUiStore((s) => s.drawerOpen);
  const toggle = useChatUiStore((s) => s.toggleDrawer);
  return { open, toggle };
}
