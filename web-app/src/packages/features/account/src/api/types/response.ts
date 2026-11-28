export interface AccountProfile {
  userId: number | null;
  name: string;
  nickname: string;
  avatarText: string;
}

export interface LoginResponse {
  /** 用户身份令牌 */
  token: string;
  /** 本次是否为新注册用户（false = 已有用户登录） */
  is_new: boolean;
}

export interface ProfileResponse {
  user_id: number;
  /** 首次注册时填写的姓名 */
  name: string;
  /** 可修改的昵称 */
  nickname: string;
}

export interface UpdateProfileResponse {
  nickname: string;
}
