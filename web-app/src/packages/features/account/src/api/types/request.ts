export interface LoginRequest {
  phone: string;
  password: string;
}

export interface ProfileRequest {
  /** 用户昵称 */
  name: string;
}
