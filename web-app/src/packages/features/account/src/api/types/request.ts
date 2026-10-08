export interface UpdateAccountRequest { name: string }

export interface DeviceTokenRequest {
  /** 设备唯一标识。TODO: 后期替换为手机号 */
  device_id: string
}
