// knowledge-api/src/api/knowledge-api.api.ts
/**
 * 知识库能力门面 —— 纯透传 features/knowledge，不做业务处理。
 */

export { KnowledgeModal } from "@ming/feature-knowledge";
export { useKnowledgeModalHook, formatFileSize } from "@ming/feature-knowledge";
export type { KnowledgeNode, KnowledgeTreeData } from "@ming/feature-knowledge";
export type {
  KnowledgeGroup,
  KnowledgeGroupFile,
} from "@ming/feature-knowledge";
