import type { BaseRequest } from "@ming/biz-common-net-api"
export interface ChatRoomRequest extends BaseRequest { query: string; reason: boolean }
