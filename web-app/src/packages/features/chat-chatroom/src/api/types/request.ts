import type { BaseRequest } from "@ming/biz-common-net-api"

export interface ChatRoomRequest extends BaseRequest {
  query: string
  reason: boolean
  /** 会话 id；为空则服务端新建，非空则追加到该会话 */
  conversation_id?: string | null
}
