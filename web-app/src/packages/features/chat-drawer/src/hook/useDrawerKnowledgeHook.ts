// chat-drawer/src/hook/useDrawerKnowledgeHook.ts
import { useKnowledgeStore } from "@ming/store";

/**
 * 知识库抽屉按钮 hook —— 封装 store 订阅，供 ui/ 层消费。
 * store selector 可能包含业务派生逻辑，ui/ 层不直接 import store。
 */
export function useDrawerKnowledgeHook() {
  const openKnowledge = useKnowledgeStore((s) => s.openKnowledge);
  return { openKnowledge };
}
