// src/packages/biz-common/net-api/src/init.ts

import type { BizHttpClientConfig } from "@ming/biz-common-net";
import { netClient } from "./net-client";

export function initNetApi(config: BizHttpClientConfig): void {
  netClient.init(config);
}