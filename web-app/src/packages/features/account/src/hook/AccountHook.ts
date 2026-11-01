// account/src/hook/AccountHook.ts
/**
 * 账号 Hook 层 —— 业务编排 + 状态管理 + 输入校验。
 *
 * 职责：
 *   - 用户资料状态（服务端为唯一数据源）
 *   - Token 生命周期编排：读缓存 → 判断 → 调 API → 写缓存
 *   - 登录页表单状态 + 输入校验（校验规则与服务端一致）
 *   - 通过 api/ 层调用网络和持久化，不直接依赖 biz-common-storage 实现
 */
import { useCallback, useEffect, useState } from "react";
import { createLogger } from "@ming/core-log";
import {
  fetchProfile,
  updateProfile,
  getSessionContext,
  setSessionContext,
  clearSessionContext,
  setDeviceId,
} from "../api";
import { login as loginApi } from "../api/account.api";
import type { LoginRequest } from "../api/types";

const log = createLogger("account/hook");

// ---------------------------------------------------------------------------
// 校验规则 —— 与服务端保持一致（服务端: app-server/.../account/schemas/bean.py）
// ---------------------------------------------------------------------------

/** 手机号：可选 + 前缀，6-20 位数字 */
const _PHONE_PATTERN = /^\+?[0-9]{6,20}$/;

/** 密码：≥8 位，含大小写字母、数字、. 或 _ 至少一个，最长 64 位 */
const _PASSWORD_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[._]).{8,64}$/;

export interface ValidationResult {
  valid: boolean;
  error: string;
}

/** 校验手机号格式 */
export function validatePhone(phone: string): ValidationResult {
  if (!phone.trim()) {
    return { valid: false, error: "请输入手机号" };
  }
  if (!_PHONE_PATTERN.test(phone.trim())) {
    return {
      valid: false,
      error: "手机号格式错误（6-20 位数字，可选 + 前缀）",
    };
  }
  return { valid: true, error: "" };
}

/** 校验密码强度 */
export function validatePassword(password: string): ValidationResult {
  if (!password) {
    return { valid: false, error: "请输入密码" };
  }
  if (password.length < 8) {
    return { valid: false, error: "密码至少 8 位" };
  }
  if (password.length > 64) {
    return { valid: false, error: "密码最长 64 位" };
  }
  if (!_PASSWORD_PATTERN.test(password)) {
    return {
      valid: false,
      error: "密码需同时包含大写字母、小写字母、数字，以及 . 或 _ 中至少一个",
    };
  }
  return { valid: true, error: "" };
}

/** 校验登录表单（手机号 + 密码） */
export function validateLoginForm(
  phone: string,
  password: string,
): { phone: ValidationResult; password: ValidationResult } {
  return {
    phone: validatePhone(phone),
    password: validatePassword(password),
  };
}

// ---------------------------------------------------------------------------
// Token 编排 —— 业务决策层：何时读缓存、何时调 API、何时写缓存
// ---------------------------------------------------------------------------

/**
 * 登录（已有缓存则跳过，否则调 API 登录/自动注册）。
 * 编排：读缓存 → 有则返回 → 无则调 API → 写缓存 → 返回 token。
 */
export async function login(
  request: LoginRequest,
): Promise<{ token: string; isNew: boolean }> {
  const existing = getSessionContext();
  if (existing?.token) return { token: existing.token, isNew: false };

  const res = await loginApi(request);

  if (!res.data?.token) {
    throw new Error("登录失败: 服务端未返回有效 token");
  }

  if (res.data.device_id) {
    setDeviceId(res.data.device_id);
  }

  setSessionContext({
    token: res.data.token,
    sessionId: res.data.session_id,
  });

  log.info("登录完成", {
    device_id: res.data.device_id?.slice(0, 12) + "...",
    session_id: res.data.session_id?.slice(0, 8) + "...",
    is_new: res.data.is_new,
  });

  return { token: res.data.token, isNew: res.data.is_new ?? false };
}

/** 重新登录（清除缓存后重新登录）。 */
export async function refreshDeviceToken(
  request: LoginRequest,
): Promise<string> {
  clearSessionContext();
  const result = await login(request);
  return result.token;
}

// ---------------------------------------------------------------------------
// 登录页 Hook —— 表单状态 + 校验 + 登录流程
// ---------------------------------------------------------------------------

export type LoginStatus = "idle" | "loading" | "success" | "error";

export interface UseLoginPageHookReturn {
  phone: string;
  password: string;
  setPhone: (v: string) => void;
  setPassword: (v: string) => void;
  phoneError: string;
  passwordError: string;
  submitError: string;
  status: LoginStatus;
  isNewUser: boolean;
  handleSubmit: () => Promise<void>;
}

export function useLoginPageHook(
  onSuccess: () => void,
): UseLoginPageHookReturn {
  const [phone, setPhoneState] = useState("");
  const [password, setPasswordState] = useState("");
  const [phoneError, setPhoneError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [status, setStatus] = useState<LoginStatus>("idle");
  const [isNewUser, setIsNewUser] = useState(false);

  const setPhone = useCallback((v: string) => {
    setPhoneState(v);
    setPhoneError("");
    setSubmitError("");
  }, []);

  const setPassword = useCallback((v: string) => {
    setPasswordState(v);
    setPasswordError("");
    setSubmitError("");
  }, []);

  const handleSubmit = useCallback(async () => {
    const validation = validateLoginForm(phone, password);
    setPhoneError(validation.phone.error);
    setPasswordError(validation.password.error);

    if (!validation.phone.valid || !validation.password.valid) {
      return;
    }

    setStatus("loading");
    setSubmitError("");

    try {
      const result = await login({
        phone: phone.trim(),
        password,
      });
      setIsNewUser(result.isNew);
      setStatus("success");
      onSuccess();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "登录失败，请稍后重试";
      setSubmitError(message);
      setStatus("error");
    }
  }, [phone, password, onSuccess]);

  return {
    phone,
    password,
    setPhone,
    setPassword,
    phoneError,
    passwordError,
    submitError,
    status,
    isNewUser,
    handleSubmit,
  };
}

// ---------------------------------------------------------------------------
// 用户资料 Hook
// ---------------------------------------------------------------------------

export function useAccount() {
  const [profile, setProfile] = useState({
    id: "",
    name: "",
    avatarText: "",
  });

  // 挂载时从服务端拉取昵称
  useEffect(() => {
    fetchProfile()
      .then((res) => {
        const name = res.data?.name;
        if (name) {
          setProfile({
            id: name.toLowerCase(),
            name,
            avatarText: name.slice(0, 1).toUpperCase(),
          });
        }
      })
      .catch(() => {
        // 服务端不可用时保持空状态
      });
  }, []);

  const update = async (name: string) => {
    const normalized = name.trim();
    if (!normalized) return profile;
    const res = await updateProfile({ name: normalized });
    const savedName = res.data?.name || normalized;
    const next = {
      id: savedName.toLowerCase(),
      name: savedName,
      avatarText: savedName.slice(0, 1).toUpperCase(),
    };
    setProfile(next);
    return next;
  };

  return { profile, update };
}
