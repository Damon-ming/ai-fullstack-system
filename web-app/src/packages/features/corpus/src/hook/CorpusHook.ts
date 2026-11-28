// corpus/src/hook/useCorpusModalHook.ts
import { useCallback, useMemo } from "react";
import { useCorpusStore } from "@ming/store";
import type { CorpusState } from "@ming/store";
import { useCorpusQuery } from "../api";
import type { CorpusNode } from "../api";
import type { CorpusViewNode } from "./types";
/** 格式化文件大小，供 Hook 构造目录树展示数据。 */
export function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} KB`;
  return `${bytes} B`;
}

function countFiles(node: CorpusNode): number {
  if (node.type === "file") return 1;
  return node.children.reduce((count, child) => count + countFiles(child), 0);
}

export function sortCorpusNodes(nodes: CorpusNode[]): CorpusNode[] {
  return [...nodes].sort((a, b) => {
    if (a.type !== b.type) return a.type === "directory" ? -1 : 1;
    if (a.type === "directory") return a.name.localeCompare(b.name);
    return (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0);
  });
}

export function formatUploadDate(value: string): string {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString()
    : "—";
}

function toViewNode(node: CorpusNode): CorpusViewNode {
  return {
    ...node,
    uploadDate: node.type === "file" ? formatUploadDate(node.created_at) : "",
    displaySize: node.type === "file" ? formatFileSize(node.size) : "",
    children: sortCorpusNodes(node.children).map(toViewNode),
  };
}

export function useCorpusModalHook() {
  const open = useCorpusStore((s: CorpusState) => s.open);
  const openCorpus = useCorpusStore((s: CorpusState) => s.openCorpus);
  const closeCorpus = useCorpusStore((s: CorpusState) => s.closeCorpus);
  const { data, isLoading, isError, refetch } = useCorpusQuery();

  const handleOpen = useCallback(() => {
    openCorpus();
    refetch();
  }, [openCorpus, refetch]);

  const totalFileCount = useMemo(
    () => (data?.data ? countFiles(data.data.root) : 0),
    [data],
  );
  const treeData = useMemo(
    () => (data?.data ? toViewNode(data.data.root) : null),
    [data],
  );

  return {
    open,
    openCorpus: handleOpen,
    closeCorpus,
    treeData,
    totalFileCount,
    isLoading,
    isError,
  };
}
