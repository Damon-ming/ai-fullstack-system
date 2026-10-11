// src/packages/biz-common/net/src/error-code.ts
/**
 * 统一错误码 —— 与服务端 error_codes.py / server_error.py 对齐。
 *
 * 格式: A BBB CCC [DD...] (7位起，无上限)
 *   A    (第1位)    — 结果位: 1=成功, 2=失败, 3-9 预留
 *   BBB  (第2-4位)  — 系统位: 000=通用, 001-999=具体子系统
 *   CCC  (第5-7位)  — 业务位: 000=通用, 001-999=具体业务
 *   DD... (第8位起) — 具体业务码: 无位数限制
 *
 * 示例:
 *   1000000 = 成功(通用)
 *   2001001 = 失败, 加密协议(001), 密钥格式错误(001)
 *   2002001 = 失败, 认证鉴权(002), 缺少Token(001)
 *   2010001 = 失败, 数据库(010), 数据库故障(001)
 */

// ---------------------------------------------------------------------------
// 结果位 (第1位)
// ---------------------------------------------------------------------------

export const SUCCESS = 1;
export const FAILURE = 2;

// ---------------------------------------------------------------------------
// 系统位 (第2-4位)
// ---------------------------------------------------------------------------

export const System = {
  GENERIC: 0, // 000 通用
  ENCRYPTION: 1, // 001 加密协议
  AUTH: 2, // 002 认证鉴权
  ACCOUNT: 3, // 003 账号体系
  CHAT: 4, // 004 AI/Chat
  UPLOAD: 5, // 005 文件上传
  // 006-099 预留系统
  DATABASE: 6, // 006 数据库/基础设施
} as const;

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
}

// ---------------------------------------------------------------------------
// 具体错误码 (完整7位起)
// ---------------------------------------------------------------------------

const _Success = {
  OK: 1000000, // 通用成功
} as const;

const _Encryption = {
  INVALID_KEY_FORMAT: 2001001, // AES 密钥格式错误
  SESSION_REG_FAILED: 2001002, // 会话注册失败
  UNSUPPORTED_VERSION: 2001003, // 不支持的加密版本
  DECRYPTION_FAILED: 2001004, // JSON 解密失败
  META_DECRYPT_FAILED: 2001005, // Meta 解密失败
  SESSION_INVALID: 2001006, // 会话无效/过期
  SIGNATURE_FAILED: 2001007, // 签名验证失败
} as const;

const _Auth = {
  MISSING_TOKEN: 2002001, // 缺少认证 Token
  INVALID_TOKEN: 2002002, // Token 无效/过期
} as const;

const _Chat = {
  TIMEOUT: 2004001, // 请求超时
  UNKNOWN: 2004002, // 未知异常
} as const;

const _Upload = {
  UPLOAD_FAILED: 2005001, // 上传失败
  IN_PROGRESS: 2005002, // 资料库正在更新中
} as const;

const _System = {
  DATABASE_FAILURE: 2006001, // 数据库故障
  ENCRYPTION_FAILURE: 2006002, // 加密子系统故障
  UPLOAD_FAILURE: 2006003, // 上传子系统故障
  AI_FAILURE: 2006004, // AI 子系统故障
  AUTH_FAILURE: 2006005, // 认证子系统故障
  UNKNOWN: 200699, // 未知系统故障（与后端 _System.UNKNOWN 一致）
} as const;

const _Validation = {
  PARAM_FORMAT: 2000001, // 请求参数格式错误
} as const;

// ---------------------------------------------------------------------------
// 统一命名空间 —— 业务代码直接引用
// ---------------------------------------------------------------------------

export const ErrorCode = {
  // 成功
  OK: _Success.OK, // 1000000

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

  // 参数校验
  VALIDATION: _Validation,
} as const;

// ---------------------------------------------------------------------------
// 子系统分类码 —— 与后端 ServerSubSystem 对齐
// ---------------------------------------------------------------------------

export const ServerSubSystem = {
  DATABASE: _System.DATABASE_FAILURE, // 2006001 数据库操作失败
  ENCRYPTION: _System.ENCRYPTION_FAILURE, // 2006002 加密/解密失败
  UPLOAD: _System.UPLOAD_FAILURE, // 2006003 上传处理失败
  AI: _System.AI_FAILURE, // 2006004 AI 推理失败
  AUTH: _System.AUTH_FAILURE, // 2006005 认证/鉴权失败
  UNKNOWN: _System.UNKNOWN, // 200699 未知子系统异常
} as const;

// ---------------------------------------------------------------------------
// 辅助函数
// ---------------------------------------------------------------------------

/**
 * 将错误码拆分为四段: [结果, 系统, 业务, 具体码]
 */
function _codeSegments(code: number): [string, string, string, string] {
  const s = String(code).padEnd(7, "0"); // 不足7位右补零
  return [s[0], s.slice(1, 4), s.slice(4, 7), s.slice(7)];
}

/** 获取结果位 (第1位) */
export function getCategory(code: number): number {
  return Number(_codeSegments(code)[0]);
}

/** 获取系统位 (第2-4位, 3位数字) */
export function getSystem(code: number): number {
  return Number(_codeSegments(code)[1]);
}

/** 获取业务位 (第5-7位, 3位数字) */
export function getBusiness(code: number): number {
  return Number(_codeSegments(code)[2]);
}

/** 获取具体业务码 (第8位起)，7位码返回 "" */
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

/** 判断是否为服务端业务码 (>= 1000000) */
export function isServerCode(code: number): boolean {
  return code >= _Success.OK;
}

/**
 * 判断业务码分类 —— 替代旧的 getBizCodeCategory
 * 返回 "success" | "fail" | "server"
 * - "success": 标准成功码 (1000000)
 * - "fail": 标准失败码 (2xxxxxx)
 * - "server": 其他服务端码（兼容未来扩展）
 */
export function getServerCodeCategory(
  code: number,
): "success" | "fail" | "server" {
  if (isSuccess(code)) return "success";
  if (isFailure(code)) return "fail";
  // 其他 >= 1000000 的码视为服务端返回（兼容未来扩展）
  if (isServerCode(code)) return "server";
  return "fail";
}

// ---------------------------------------------------------------------------
// 兼容旧名（过渡期保留，防止外部引用 BizCodeRange 报错）
// ---------------------------------------------------------------------------

/** @deprecated 使用 ErrorCode 命名空间替代 */
export const BizCodeRange = {
  SUCCESS_MIN: 1000000,
  SUCCESS_NO_CONTENT: 1000000,
  SUCCESS_MAX: 1999999,
  AI_SUCCESS_MIN: 1000000,
  AI_SUCCESS_MAX: 1999999,
  AI_FAIL_MIN: 2000000,
  AI_FAIL_MAX: 2999999,
  FAIL_MIN: 2000000,
  FAIL_MAX: 2999999,
} as const;

/** @deprecated 使用 getServerCodeCategory 替代 */
export function getBizCodeCategory(
  code: number,
): "success" | "fail" | "server" {
  return getServerCodeCategory(code);
}
