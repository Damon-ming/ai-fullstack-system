export interface LoginRequest {
  phone: string;
  password: string;
  /** 首次注册必填，已有账号登录可省略 */
  name?: string;
}

export interface UpdateProfileRequest {
  /** 用户昵称 */
  nickname: string;
}
