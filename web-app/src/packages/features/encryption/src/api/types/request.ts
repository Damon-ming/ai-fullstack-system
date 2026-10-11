// web-app/src/packages/features/encryption/src/api/types/request.ts

/** 会话注册请求 —— 客户端将 RSA 加密后的 AES 密钥发送给服务端 */
export interface SessionRegisterRequest {
  encryptedAesKey: string; // base64，RSA-OAEP 加密的 AES-256 密钥
}
