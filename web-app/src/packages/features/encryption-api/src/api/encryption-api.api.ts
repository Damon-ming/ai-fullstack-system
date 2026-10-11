// web-app/src/packages/features/encryption-api/src/api/encryption-api.api.ts
/**
 * 加密能力门面 —— 纯透传 features/encryption，不做业务处理。
 *
 * store 写入由 bootstrap 完成（与 token 模式一致）。
 */
import { exchangeKeys as exchangeKeysInFeature } from "@ming/features-encryption";

export const exchangeKeys = () => exchangeKeysInFeature();
