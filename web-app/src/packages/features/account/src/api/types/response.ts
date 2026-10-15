export interface AccountProfile {
  id: string;
  name: string;
  avatarText: string;
}

export interface DeviceTokenResponse {
  /** 用户身份令牌 */
  token: string
  /** 服务端根据 UA 计算的设备唯一标识 */
  device_id: string
  /** token + device_id 组合的会话标识（加密绑定粒度） */
  session_id: string
}

export interface ProfileResponse {
  /** 用户昵称 */
  name: string
}
