// web-app/src/packages/features/chat-drawer/src/hook/useDrawerCorpusHook.ts
import { useCorpusStore } from "@ming/store";
import type { CorpusState } from "@ming/store";

/**
 * 知识库抽屉按钮 hook —— 封装 store 订阅，供 ui/ 层消费。
 * store selector 可能包含业务派生逻辑，ui/ 层不直接 import store。
 */
export function useDrawerCorpusHook() {
  const openCorpus = useCorpusStore((s: CorpusState) => s.openCorpus);
  return { openCorpus };
}
