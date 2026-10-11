// web-app/src/packages/features/encryption/src/api/types/response.ts

/** 服务端返回的公钥信息 */
export interface PublicKeyResponse {
  publicKey: string; // PEM 格式
  algorithm: string; // "RSA-OAEP-256"
}

/** 会话注册响应 */
export interface SessionResponse {
  keyId: string;
  expiresIn: number; // 秒
}
