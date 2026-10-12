export interface UpdateAccountRequest { name: string }

export interface DeviceTokenRequest {
  /**
   * 用户手机号（含区号）。
   * TODO: 当前模拟为随机字符串，后期替换为用户真实输入的手机号 + 验证码
   */
  phone: string
}
