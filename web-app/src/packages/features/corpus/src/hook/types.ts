import type { CorpusNode } from "../api";

/** Hook 为目录树 UI 准备好的展示节点。 */
export type CorpusViewNode = Omit<CorpusNode, "children"> & {
  uploadDate: string;
  displaySize: string;
  children: CorpusViewNode[];
};
