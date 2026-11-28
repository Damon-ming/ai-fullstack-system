// corpus/src/hook/types.ts
/**
 * 模块内部 UI ↔ Hook 通讯类型（非网络请求）。
 */

/** 按日期分组的文件列表 —— UI 直接渲染，不做额外处理 */
export interface CorpusGroup {
  date: string;
  dateLabel: string;
  files: CorpusGroupFile[];
}

export interface CorpusGroupFile {
  name: string;
  path: string;
  sizeMB: string;
  uploader: string;
}
