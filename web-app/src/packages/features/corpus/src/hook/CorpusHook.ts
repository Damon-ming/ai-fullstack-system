// corpus/src/hook/useCorpusModalHook.ts
import { useCallback, useMemo } from "react";
import { useCorpusStore } from "@ming/store";
import { useCorpusQuery } from "../api";
import type { CorpusNode } from "../api";
import type { CorpusGroup } from "./types";

export type { CorpusGroup, CorpusGroupFile } from "./types";

/** 格式化文件大小 —— 共享工具函数，hook/UI 均可使用 */
export function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} KB`;
  return `${bytes} B`;
}

/** 扁平化收集所有文件节点 */
function collectFiles(nodes: CorpusNode[]): CorpusNode[] {
  const result: CorpusNode[] = [];
  for (const node of nodes) {
    if (node.type === "file") result.push(node);
    else result.push(...collectFiles(node.children));
  }
  return result;
}

/** 按日期分组，日期降序 */
function groupByDate(files: CorpusNode[]): CorpusGroup[] {
  const groups = new Map<string, CorpusNode[]>();
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

export function useCorpusModalHook() {
  const open = useCorpusStore((s) => s.open);
  const openCorpus = useCorpusStore((s) => s.openCorpus);
  const closeCorpus = useCorpusStore((s) => s.closeCorpus);
  const { data, isLoading, isError, refetch } = useCorpusQuery();

  const handleOpen = useCallback(() => {
    openCorpus();
    refetch();
  }, [openCorpus, refetch]);

  const corpusGroups = useMemo(() => {
    const tree = data?.data;
    if (!tree) return [];
    const files = collectFiles(tree.root.children);
    return groupByDate(files);
  }, [data]);

  const totalFileCount = useMemo(
    () => corpusGroups.reduce((sum, g) => sum + g.files.length, 0),
    [corpusGroups],
  );

  return {
    open,
    openCorpus: handleOpen,
    closeCorpus,
    treeData: data?.data ?? null,
    corpusGroups,
    totalFileCount,
    isLoading,
    isError,
  };
}
