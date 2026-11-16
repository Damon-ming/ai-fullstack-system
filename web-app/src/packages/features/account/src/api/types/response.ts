export interface AccountProfile {
  id: string;
  name: string;
  avatarText: string;
}

export interface LoginResponse {
  /** 用户身份令牌 */
  token: string;
  /** 本次是否为新注册用户（false = 已有用户登录） */
  is_new: boolean;
}

export interface ProfileResponse {
  /** 用户昵称 */
  name: string;
}
