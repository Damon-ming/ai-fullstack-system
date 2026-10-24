import { useCallback } from "react";
import { queryFactory } from "@ming/data-layer";
import { useKnowledgeStore } from "@ming/store";
import { fetchKnowledgeTree } from "../api/knowledge.api";
import type { KnowledgeTreeData } from "../api/types/knowledge";

const KNOWLEDGE_TREE_KEY = ["knowledge", "tree"] as const;

const useKnowledgeQuery = queryFactory.createQueryHook<KnowledgeTreeData>(
  KNOWLEDGE_TREE_KEY,
  fetchKnowledgeTree,
  { staleTime: 30_000, refetchOnWindowFocus: false },
);

export function useDrawerKnowledgeHook() {
  const open = useKnowledgeStore((s) => s.open);
  const openKnowledge = useKnowledgeStore((s) => s.openKnowledge);
  const closeKnowledge = useKnowledgeStore((s) => s.closeKnowledge);
  const { data, isLoading, isError, refetch } = useKnowledgeQuery();

  const handleOpen = useCallback(() => {
    openKnowledge();
    refetch();
  }, [openKnowledge, refetch]);

  return {
    open,
    openKnowledge: handleOpen,
    closeKnowledge,
    treeData: data?.data ?? null,
    isLoading,
    isError,
  };
}
