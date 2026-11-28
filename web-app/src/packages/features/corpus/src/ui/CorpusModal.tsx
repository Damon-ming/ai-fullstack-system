// web-app/src/packages/features/corpus/src/ui/CorpusModal.tsx
import React, { useState } from "react";
import { useCorpusModalHook } from "../hook";
import { useTranslation } from "@ming/i18n";
import type { CorpusViewNode } from "../hook";

/** 递归渲染目录树节点 */
function TreeItem({
  node,
  depth,
}: Readonly<{ node: CorpusViewNode; depth: number }>) {
  const [expanded, setExpanded] = useState(true);

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
      <span className="shrink-0 text-xs text-gray-400">{node.uploadDate}</span>
      <span className="shrink-0 text-xs text-gray-400">{node.displaySize}</span>
      <button
        type="button"
        className="shrink-0 rounded p-1 text-xs text-gray-400 transition hover:bg-red-50 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-30"
        disabled
        title="删除功能开发中"
      >
        ✕
      </button>
    </div>
  );
}

export function CorpusModal() {
  const { t } = useTranslation("corpus");
  const { open, closeCorpus, treeData, totalFileCount, isLoading, isError } =
    useCorpusModalHook();

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={closeCorpus}
    >
      <section
        role="dialog"
        className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-3xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-base font-semibold text-gray-800">
            {t("corpus.title")}
          </h2>
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-full text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
            onClick={closeCorpus}
            aria-label={t("corpus.close")}
          >
            ✕
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-sm text-gray-400">
              {t("corpus.loading")}
            </div>
          )}
          {isError && (
            <div className="flex items-center justify-center py-12 text-sm text-red-500">
              {t("corpus.error")}
            </div>
          )}
          {!isLoading && !isError && totalFileCount === 0 && (
            <div className="flex items-center justify-center py-12 text-sm text-gray-400">
              {t("corpus.empty")}
            </div>
          )}
          {!isLoading && !isError && totalFileCount > 0 && (
            <>
              <TreeItem node={treeData!} depth={0} />
            </>
          )}
        </div>

        {/* 底部 */}
        {totalFileCount > 0 && (
          <div className="border-t border-gray-100 px-6 py-3 text-xs text-gray-400">
            {t("corpus.fileCount", { count: totalFileCount })}
          </div>
        )}
      </section>
    </div>
  );
}
