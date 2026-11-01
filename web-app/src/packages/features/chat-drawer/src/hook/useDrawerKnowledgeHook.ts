import { useCallback, useMemo } from "react";
import { queryFactory } from "@ming/data-layer";
import { useKnowledgeStore } from "@ming/store";
import { fetchKnowledgeTree } from "../api/knowledge.api";
import type { KnowledgeNode, KnowledgeTreeData } from "../api/types/knowledge";

const KNOWLEDGE_TREE_KEY = ["knowledge", "tree"] as const;

const useKnowledgeQuery = queryFactory.createQueryHook<KnowledgeTreeData>(
  KNOWLEDGE_TREE_KEY,
  fetchKnowledgeTree,
  { staleTime: 30_000, refetchOnWindowFocus: false },
);

/** 按日期分组的文件列表 — UI 直接渲染，不做额外处理 */
export interface KnowledgeGroup {
  date: string;
  dateLabel: string;
  files: KnowledgeGroupFile[];
}

export interface KnowledgeGroupFile {
  name: string;
  path: string;
  sizeMB: string;
}

/** 扁平化收集所有文件节点 */
function collectFiles(nodes: KnowledgeNode[]): KnowledgeNode[] {
  const result: KnowledgeNode[] = [];
  for (const node of nodes) {
    if (node.type === "file") result.push(node);
    else result.push(...collectFiles(node.children));
  }
  return result;
}

/** 按日期分组，日期降序 */
function groupByDate(files: KnowledgeNode[]): KnowledgeGroup[] {
  const groups = new Map<string, KnowledgeNode[]>();
  for (const file of files) {
    const key = file.created_at
      ? new Date(file.created_at).toISOString().slice(0, 10)
      : "unknown";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(file);
  }
  return [...groups.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([date, items]) => {
      const d = new Date(date);
      return {
        date,
        dateLabel: `${d.getMonth() + 1}月${d.getDate()}日`,
        files: items.map((f) => ({
          name: f.name,
          path: f.path,
          sizeMB: `${(f.size / (1024 * 1024)).toFixed(2)} MB`,
        })),
      };
    });
}

export function useDrawerKnowledgeHook() {
  const open = useKnowledgeStore((s) => s.open);
  const openKnowledge = useKnowledgeStore((s) => s.openKnowledge);
  const closeKnowledge = useKnowledgeStore((s) => s.closeKnowledge);
  const { data, isLoading, isError, refetch } = useKnowledgeQuery();

  const handleOpen = useCallback(() => {
    openKnowledge();
    refetch();
  }, [openKnowledge, refetch]);

  const knowledgeGroups = useMemo(() => {
    const tree = data?.data;
    if (!tree) return [];
    const files = collectFiles(tree.root.children);
    return groupByDate(files);
  }, [data]);

  const totalFileCount = useMemo(
    () => knowledgeGroups.reduce((sum, g) => sum + g.files.length, 0),
    [knowledgeGroups],
  );

  return {
    open,
    openKnowledge: handleOpen,
    closeKnowledge,
    treeData: data?.data ?? null,
    knowledgeGroups,
    totalFileCount,
    isLoading,
    isError,
  };
}
