import React, { useState } from "react";
import { useDrawerKnowledgeHook } from "../hook/useDrawerKnowledgeHook";
import { useTranslation } from "@ming/i18n";
import type { KnowledgeNode } from "../api/types/knowledge";
import type { KnowledgeGroup } from "../hook/useDrawerKnowledgeHook";

/** 递归渲染目录树节点 */
function TreeItem({ node, depth }: { node: KnowledgeNode; depth: number }) {
  const [expanded, setExpanded] = useState(depth === 0);

  if (node.type === "directory") {
    const hasChildren = node.children.length > 0;
    return (
      <div>
        <button
          type="button"
          className="flex w-full items-center gap-1 rounded px-2 py-1 text-left text-sm text-gray-600 transition hover:bg-gray-100"
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => hasChildren && setExpanded((v) => !v)}
          disabled={!hasChildren}
        >
          <span className="w-4 text-center text-xs text-gray-400">
            {hasChildren ? (expanded ? "▾" : "▸") : "·"}
          </span>
          <span className="font-medium">{node.name}</span>
        </button>
        {expanded && hasChildren && (
          <div>
            {node.children.map((child) => (
              <TreeItem
                key={`${child.type}-${child.path}`}
                node={child}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-2 rounded px-2 py-1 text-sm text-gray-500 transition hover:bg-gray-50"
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
    >
      <span className="w-4 text-center text-xs text-gray-300">·</span>
      <span className="flex-1 truncate text-gray-700">{node.name}</span>
      <span className="shrink-0 text-xs text-gray-400">
        {node.size >= 1024 * 1024
          ? `${(node.size / (1024 * 1024)).toFixed(2)} MB`
          : node.size >= 1024
            ? `${(node.size / 1024).toFixed(1)} KB`
            : `${node.size} B`}
      </span>
    </div>
  );
}

/** 按日期分组的文件列表 — 纯展示，数据由 hook 预处理好 */
function DateGroupedList({ groups }: { groups: KnowledgeGroup[] }) {
  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div key={group.date}>
          <div className="sticky top-0 z-10 bg-white px-3 py-1.5 text-xs font-medium text-gray-500">
            {group.dateLabel} · {group.files.length} 个文件
          </div>
          <div className="space-y-0.5">
            {group.files.map((file) => (
              <div
                key={file.path}
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition hover:bg-gray-50"
              >
                <span className="flex-1 truncate text-gray-700">
                  {file.name}
                </span>
                <span className="shrink-0 text-xs text-gray-400">
                  {file.sizeMB}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export const KnowledgeModal: React.FC = () => {
  const { t } = useTranslation("chat-drawer");
  const {
    open,
    closeKnowledge,
    treeData,
    knowledgeGroups,
    totalFileCount,
    isLoading,
    isError,
  } = useDrawerKnowledgeHook();
  const [tab, setTab] = useState<"tree" | "list">("list");

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={closeKnowledge}
    >
      <section
        role="dialog"
        className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-3xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-base font-semibold text-gray-800">
            {t("knowledge.title")}
          </h2>
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-full text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
            onClick={closeKnowledge}
            aria-label={t("knowledge.close")}
          >
            ✕
          </button>
        </div>

        {/* 切换 tab */}
        <div className="flex gap-1 border-b border-gray-100 px-6 pt-2">
          <button
            type="button"
            className={`rounded-t-lg px-3 py-1.5 text-sm font-medium transition ${
              tab === "list"
                ? "bg-gray-100 text-gray-800"
                : "text-gray-400 hover:text-gray-600"
            }`}
            onClick={() => setTab("list")}
          >
            {t("knowledge.tabList")}
          </button>
          <button
            type="button"
            className={`rounded-t-lg px-3 py-1.5 text-sm font-medium transition ${
              tab === "tree"
                ? "bg-gray-100 text-gray-800"
                : "text-gray-400 hover:text-gray-600"
            }`}
            onClick={() => setTab("tree")}
          >
            {t("knowledge.tabTree")}
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-sm text-gray-400">
              {t("knowledge.loading")}
            </div>
          )}
          {isError && (
            <div className="flex items-center justify-center py-12 text-sm text-red-500">
              {t("knowledge.error")}
            </div>
          )}
          {!isLoading && !isError && totalFileCount === 0 && (
            <div className="flex items-center justify-center py-12 text-sm text-gray-400">
              {t("knowledge.empty")}
            </div>
          )}
          {!isLoading && !isError && totalFileCount > 0 && (
            <>
              {tab === "list" && <DateGroupedList groups={knowledgeGroups} />}
              {tab === "tree" && <TreeItem node={treeData!.root} depth={0} />}
            </>
          )}
        </div>

        {/* 底部 */}
        {totalFileCount > 0 && (
          <div className="border-t border-gray-100 px-6 py-3 text-xs text-gray-400">
            {t("knowledge.fileCount", { count: totalFileCount })}
          </div>
        )}
      </section>
    </div>
  );
};
