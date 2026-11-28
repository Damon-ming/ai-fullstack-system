// corpus-api/src/api/corpus-api.api.ts
/**
 * 知识库能力门面 —— 纯透传 features/corpus，不做业务处理。
 */

export { CorpusModal } from "@ming/feature-corpus";
export { useCorpusModalHook, formatFileSize } from "@ming/feature-corpus";
export type { CorpusNode, CorpusTreeData } from "@ming/feature-corpus";
