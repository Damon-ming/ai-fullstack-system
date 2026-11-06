// knowledge/src/hook/useKnowledgeModalHook.ts
import { useCallback, useMemo } from "react";
import { useKnowledgeStore } from "@ming/store";
import { useKnowledgeQuery } from "../api";
import type { KnowledgeNode } from "../api";
import type { KnowledgeGroup } from "./types";

export type { KnowledgeGroup, KnowledgeGroupFile } from "./types";

/** 格式化文件大小 —— 共享工具函数，hook/UI 均可使用 */
export function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} KB`;
  return `${bytes} B`;
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
          sizeMB: formatFileSize(f.size),
          uploader: f.uploader,
        })),
      };
    });
}

export function useKnowledgeModalHook() {
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
