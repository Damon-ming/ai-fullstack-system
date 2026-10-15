// src/packages/biz-common/net/src/error-code.ts
/**
 * 统一错误码 —— 与服务端 error_codes.py / server_error.py 对齐。
 *
 * 格式: A BB CCC DDD (9位)
 *   A    (第1位)    — 结果位: 1=成功, 2=失败, 3-9 预留
 *   BB   (第2-3位)  — 系统位: 00=当前服务(默认), 01-99=预留, 拆子系统时启用
 *   CCC  (第4-6位)  — 业务模块位: 000=通用, 001=参数校验, 002=加密, 003=认证...
 *   DDD  (第7-9位)  — 具体业务码: 同模块内递增
 *
 * 示例:
 *   100000000 = 成功(通用)
 *   200002001 = 失败, 当前服务, 加密模块(002), AES密钥格式错误(001)
 *   200003001 = 失败, 当前服务, 认证模块(003), 缺少Token(001)
 *   200005001 = 失败, 当前服务, Chat模块(005), 请求超时(001)
 */

// ---------------------------------------------------------------------------
// 结果位 (第1位)
// ---------------------------------------------------------------------------

export const SUCCESS = 1;
export const FAILURE = 2;

// ---------------------------------------------------------------------------
// 系统位 (第2-3位) — 当前统一为 00, 拆子系统时启用
// ---------------------------------------------------------------------------

export const System = {
  GENERIC: 0, // 00 当前服务(默认)
  // 01-99 预留, 等拆子系统时启用
} as const;

// ---------------------------------------------------------------------------
// 业务模块位 (CCC, 第4-6位)
// ---------------------------------------------------------------------------

export const Business = {
  GENERIC: 0, // 000 通用
  VALIDATION: 1, // 001 参数校验
  ENCRYPTION: 2, // 002 加密协议
  AUTH: 3, // 003 认证鉴权
  ACCOUNT: 4, // 004 账号体系
  CHAT: 5, // 005 AI/Chat
  UPLOAD: 6, // 006 文件上传
  SYSTEM: 7, // 007 系统/基础设施
} as const;

// ---------------------------------------------------------------------------
// 辅助函数 — 组装完整错误码 (与服务端 _build 对齐)
// ---------------------------------------------------------------------------

function _build(detail: number, business: number = 0, system: number = 0, result: number = 2): number {
  return Number(`${result}${String(system).padStart(2, "0")}${String(business).padStart(3, "0")}${String(detail).padStart(3, "0")}`);
}

// ---------------------------------------------------------------------------
// 客户端错误码 (1-10) —— 纯客户端场景，不来自服务端
// ---------------------------------------------------------------------------

export enum ClientErrorCode {
  /** 网络超时（含 axios timeout / fetch timeout） */
  NET_TIMEOUT = 1,
  /** 请求配置错误（如缺少 token、URL 非法） */
  CONFIG_ERR = 2,
  /** 请求被主动取消（用户操作 / AbortController） */
  CONFIG_CANCEL = 3,
  /** 服务不可达（服务端未启动、连接被拒、DNS 失败、主机不可达） */
  NET_UNREACHABLE = 4,
}

// ---------------------------------------------------------------------------
// 具体错误码 (完整10位)
// ---------------------------------------------------------------------------

const _Success = {
  OK: 100000000, // 通用成功
} as const;

const _Encryption = {
  INVALID_KEY_FORMAT: _build(1, Business.ENCRYPTION),      // 200002001 AES 密钥格式错误
  SESSION_REG_FAILED: _build(2, Business.ENCRYPTION),      // 200002002 会话注册失败
  UNSUPPORTED_VERSION: _build(3, Business.ENCRYPTION),     // 200002003 不支持的加密版本
  DECRYPTION_FAILED: _build(4, Business.ENCRYPTION),       // 200002004 JSON 解密失败
  META_DECRYPT_FAILED: _build(5, Business.ENCRYPTION),     // 200002005 Meta 解密失败
  SESSION_INVALID: _build(6, Business.ENCRYPTION),         // 200002006 会话无效/过期
  SIGNATURE_FAILED: _build(7, Business.ENCRYPTION),        // 200002007 签名验证失败
  UNSUPPORTED_SIGNATURE_VERSION: _build(8, Business.ENCRYPTION), // 200002008 不支持的签名协议版本
} as const;

const _Auth = {
  MISSING_TOKEN: _build(1, Business.AUTH),                 // 200003001 缺少认证 Token
  INVALID_TOKEN: _build(2, Business.AUTH),                 // 200003002 Token 无效/过期
} as const;

const _Chat = {
  TIMEOUT: _build(1, Business.CHAT),                       // 200005001 请求超时
  UNKNOWN: _build(2, Business.CHAT),                       // 200005002 未知异常
} as const;

const _Upload = {
  UPLOAD_FAILED: _build(1, Business.UPLOAD),               // 200006001 上传失败
  IN_PROGRESS: _build(2, Business.UPLOAD),                 // 200006002 资料库正在更新中
} as const;

const _System = {
  DATABASE_FAILURE: _build(1, Business.SYSTEM),            // 200007001 数据库故障
  ENCRYPTION_FAILURE: _build(2, Business.SYSTEM),          // 200007002 加密子系统故障
  UPLOAD_FAILURE: _build(3, Business.SYSTEM),              // 200007003 上传子系统故障
  AI_FAILURE: _build(4, Business.SYSTEM),                  // 200007004 AI 子系统故障
  AUTH_FAILURE: _build(5, Business.SYSTEM),                // 200007005 认证子系统故障
  UNKNOWN: _build(99, Business.SYSTEM),                    // 200007099 未知系统故障
} as const;

const _Validation = {
  PARAM_FORMAT: _build(1, Business.VALIDATION),            // 200001001 请求参数格式错误
} as const;

// ---------------------------------------------------------------------------
// 统一命名空间 —— 业务代码直接引用
// ---------------------------------------------------------------------------

export const ErrorCode = {
  // 成功
  OK: _Success.OK, // 100000000

  // 参数校验
  VALIDATION: _Validation,

  // 加密协议
  ENCRYPT: _Encryption,

  // 认证鉴权
  AUTH: _Auth,

  // AI/Chat
  CHAT: _Chat,

  // 文件上传
  UPLOAD: _Upload,

  // 系统/基础设施
  SYSTEM: _System,
} as const;

// ---------------------------------------------------------------------------
// 子系统分类码 —— 与后端 ServerSubSystem 对齐
// ---------------------------------------------------------------------------

export const ServerSubSystem = {
  DATABASE: _System.DATABASE_FAILURE, // 200007001 数据库操作失败
  ENCRYPTION: _System.ENCRYPTION_FAILURE, // 200007002 加密/解密失败
  UPLOAD: _System.UPLOAD_FAILURE, // 200007003 上传处理失败
  AI: _System.AI_FAILURE, // 200007004 AI 推理失败
  AUTH: _System.AUTH_FAILURE, // 200007005 认证/鉴权失败
  UNKNOWN: _System.UNKNOWN, // 200007099 未知子系统异常
} as const;

// ---------------------------------------------------------------------------
// 辅助函数
// ---------------------------------------------------------------------------

/**
 * 将错误码拆分为四段: [结果, 系统, 业务模块, 具体码]
 */
function _codeSegments(code: number): [string, string, string, string] {
  const s = String(code).padEnd(9, "0"); // 不足9位右补零
  return [s[0], s.slice(1, 3), s.slice(3, 6), s.slice(6, 9)];
}

/** 获取结果位 (第1位) */
export function getCategory(code: number): number {
  return Number(_codeSegments(code)[0]);
}

/** 获取系统位 (第2-3位, 2位数字) */
export function getSystem(code: number): number {
  return Number(_codeSegments(code)[1]);
}

/** 获取业务模块位 (第4-6位, 3位数字) */
export function getBusiness(code: number): number {
  return Number(_codeSegments(code)[2]);
}

/** 获取具体业务码 (第7-9位, 3位数字字符串) */
export function getDetail(code: number): string {
  return _codeSegments(code)[3];
}

/** 判断是否成功码 */
export function isSuccess(code: number): boolean {
  return getCategory(code) === SUCCESS;
}

/** 判断是否失败码 */
export function isFailure(code: number): boolean {
  return getCategory(code) === FAILURE;
}

/** 判断是否为服务端业务码 (>= 100000000) */
export function isServerCode(code: number): boolean {
  return code >= _Success.OK;
}

/**
 * 判断业务码分类 
 * 返回 "success" | "fail" | "server"
 */
export function getServerCodeCategory(
  code: number,
): "success" | "fail" | "server" {
  if (isSuccess(code)) return "success";
  if (isFailure(code)) return "fail";
  if (isServerCode(code)) return "server";
  return "fail";
}
